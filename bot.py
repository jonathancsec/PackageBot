import asyncio
import logging
import os
import time
from collections import defaultdict, deque
from math import ceil
from typing import Callable, Optional

import discord
from discord import app_commands
from discord.ext import tasks
from dotenv import load_dotenv

from tracker import (
    TrackingError,
    TrackingEvent,
    TrackingInfo,
    close_session,
    normalize_tracking_number,
    status_colour,
    status_emoji,
    track_package,
    tracking_url,
)
from database import (
    MAX_ACTIVE_PACKAGES_PER_USER,
    add_package,
    archive_package,
    get_active_subscriptions,
    get_package,
    get_packages,
    get_settings,
    initialize_database,
    prune_archived,
    remove_package,
    set_paused,
    set_setting,
    update_package_status,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
# Optional: used only to remove old server-specific command registrations.
GUILD_ID = os.getenv("GUILD_ID")

POLL_MINUTES = 15
STALE_DAYS = 30
MAX_CONCURRENT_LOOKUPS = 3
HISTORY_EVENT_COUNT = 10

COMMAND_COOLDOWN_SECONDS = 5
OTHER_ACTION_LIMIT = 10
OTHER_ACTION_WINDOW_SECONDS = 60
last_command_requests = {}
other_action_requests = defaultdict(deque)


# ---------- Rate limiting ----------

def get_rate_limit_delay(user_id: int, action: str):
    now = time.monotonic()

    if action == "command":
        previous_request = last_command_requests.get(user_id)
        if previous_request is not None:
            remaining = COMMAND_COOLDOWN_SECONDS - (now - previous_request)
            if remaining > 0:
                return remaining

        last_command_requests[user_id] = now
        return None

    requests = other_action_requests[user_id]
    while requests and now - requests[0] >= OTHER_ACTION_WINDOW_SECONDS:
        requests.popleft()

    if len(requests) >= OTHER_ACTION_LIMIT:
        return OTHER_ACTION_WINDOW_SECONDS - (now - requests[0])

    requests.append(now)
    return None


def prune_rate_limits():
    """Drop stale entries so these dicts don't grow forever."""
    now = time.monotonic()

    for user_id, timestamp in list(last_command_requests.items()):
        if now - timestamp >= COMMAND_COOLDOWN_SECONDS:
            del last_command_requests[user_id]

    for user_id, requests in list(other_action_requests.items()):
        while requests and now - requests[0] >= OTHER_ACTION_WINDOW_SECONDS:
            requests.popleft()
        if not requests:
            del other_action_requests[user_id]


async def reject_if_rate_limited(interaction: discord.Interaction, action: str):
    delay = get_rate_limit_delay(interaction.user.id, action)
    if delay is None:
        return False

    if action == "command":
        message = f"Please wait {delay:.1f} seconds before using another slash command."
    else:
        message = (
            "You've reached the limit of 10 other actions per minute. "
            f"Please try again in {ceil(delay)} seconds."
        )

    await interaction.response.send_message(message, ephemeral=True)
    return True


# ---------- Formatting helpers ----------

def package_name(label: Optional[str], tracking_number: str) -> str:
    return f"**{label}** (`{tracking_number}`)" if label else f"`{tracking_number}`"


def format_time(event: TrackingEvent) -> str:
    if event.occurred_at:
        return f"<t:{int(event.occurred_at.timestamp())}:f>"
    return event.raw_time


def limit_message() -> str:
    return (
        f"❌ You're already tracking {MAX_ACTIVE_PACKAGES_PER_USER} active packages. "
        "Use `/untrack` to remove one first."
    )


def build_tracking_embed(info: TrackingInfo, label: Optional[str] = None) -> discord.Embed:
    emoji = status_emoji(info.milestone)
    embed = discord.Embed(
        title=f"{emoji} {label or 'Package Tracking'}",
        description=f"`{info.tracking_number}`",
        url=tracking_url(info.tracking_number),
        colour=discord.Colour(status_colour(info.milestone)),
    )

    latest = info.latest_event

    embed.add_field(name="🚚 Carrier", value=info.carrier, inline=True)
    embed.add_field(name="📊 Status", value=info.status_text, inline=True)
    embed.add_field(
        name="📍 Location",
        value=latest.location if latest else "Unknown",
        inline=True
    )
    embed.add_field(
        name="📝 Latest Update",
        value=(latest.status[:1000] if latest else "No events yet"),
        inline=False
    )
    embed.add_field(
        name="🕐 Last Updated",
        value=format_time(latest) if latest else "Unknown",
        inline=True
    )
    embed.add_field(
        name="📅 Estimated Delivery",
        value=info.estimated_delivery or "Not available",
        inline=True
    )
    embed.set_footer(text="Tracking information provided by Ship24")
    return embed


def build_history_embed(info: TrackingInfo, label: Optional[str] = None) -> discord.Embed:
    embed = discord.Embed(
        title=f"📜 History: {label or info.tracking_number}",
        url=tracking_url(info.tracking_number),
        colour=discord.Colour(status_colour(info.milestone)),
    )

    if not info.events:
        embed.description = "No tracking events yet."
    else:
        lines = []
        for event in info.events[:HISTORY_EVENT_COUNT]:
            line = f"{format_time(event)}: **{event.status[:200]}**"
            if event.location != "Unknown":
                line += f"\n📍 {event.location}"
            lines.append(line)

        embed.description = "\n\n".join(lines)[:4000]
        if len(info.events) > HISTORY_EVENT_COUNT:
            embed.set_footer(
                text=f"Showing the latest {HISTORY_EVENT_COUNT} of {len(info.events)} events"
            )

    return embed


def build_update_message(name: str, previous: str, current: str, milestone: str) -> str:
    if milestone == "delivered":
        return f"✅ {name} was **delivered**! I've stopped tracking it."
    if milestone == "out_for_delivery":
        return f"🚚 {name} is **out for delivery** and should arrive today!"
    if milestone == "available_for_pickup":
        return f"🏬 {name} is **available for pickup**."
    if milestone == "failed_attempt":
        return f"⚠️ A delivery attempt for {name} **failed**. Check with the carrier."
    if milestone == "exception":
        return f"🚨 There's a delivery **exception** for {name}. Check with the carrier."
    return f"📦 Status update for {name}: **{previous}** → **{current}**"


def settings_text(settings: dict) -> str:
    channel_id = settings["notify_channel_id"]
    lines = [
        f"**Responses:** {'public' if settings['public_responses'] else 'private'}",
        f"**Notifications:** {'on' if settings['notifications_enabled'] else 'muted'}",
        f"**Send updates to:** {f'<#{channel_id}>' if channel_id else 'direct messages'}",
    ]
    if channel_id:
        lines.append(
            "-# Anyone who can see that channel can see your updates. "
            "If I can't post there, I'll fall back to DMs."
        )
    return "\n".join(lines)


async def ephemeral_for(user_id: int) -> bool:
    settings = await get_settings(str(user_id))
    return not settings["public_responses"]


# ---------- Client ----------

class MyClient(discord.Client):
    def __init__(self):
        intents = discord.Intents.default()
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self):
        await initialize_database()

        # Remove old guild-only command registrations from the development server,
        # if GUILD_ID is still configured. Commands are registered globally below.
        if GUILD_ID:
            try:
                guild = discord.Object(id=int(GUILD_ID))
                self.tree.clear_commands(guild=guild)
                await self.tree.sync(guild=guild)
            except ValueError:
                logger.warning("GUILD_ID is not a valid integer; skipping old guild-command cleanup.")
            except discord.HTTPException:
                logger.exception("Could not clean up old server-specific slash commands.")

        synced = await self.tree.sync()
        logger.info("Synced %s global slash command(s).", len(synced))

        self.check_package_updates.start()
        self.housekeeping.start()

    async def close(self):
        await close_session()
        await super().close()

    # ----- Notifications -----

    async def notify_user(self, user_id: str, channel_id: Optional[str], content: str) -> bool:
        """Try the user's chosen channel first, then fall back to DMs."""
        uid = int(user_id)

        if channel_id:
            try:
                channel = self.get_channel(int(channel_id)) or await self.fetch_channel(int(channel_id))
                if isinstance(channel, discord.abc.Messageable):
                    await channel.send(
                        f"<@{uid}> {content}",
                        allowed_mentions=discord.AllowedMentions(
                            users=[discord.Object(id=uid)]
                        ),
                    )
                    return True
            except (discord.Forbidden, discord.NotFound):
                logger.info("Can't post in channel %s; falling back to DM for user %s", channel_id, uid)
            except discord.HTTPException:
                logger.warning("Failed to post in channel %s; falling back to DM", channel_id)

        try:
            user = await self.fetch_user(uid)
            await user.send(content)
            return True
        except discord.Forbidden:
            logger.info("User %s has DMs closed; couldn't deliver notification.", uid)
        except discord.HTTPException:
            logger.warning("Failed to DM user %s", uid, exc_info=True)

        return False

    async def process_subscription(self, sub: dict, info: TrackingInfo):
        user_id = sub["user_id"]
        number = sub["tracking_number"]
        label = sub["label"]
        previous = sub["status"] or "Unknown"
        current = info.status_text
        name = package_name(label, number)

        if current != previous:
            # Save first, so a failed notification never causes endless retries.
            await update_package_status(user_id, number, current, archived=info.is_delivered)

            if sub["notifications_enabled"]:
                await self.notify_user(
                    user_id,
                    sub["notify_channel_id"],
                    build_update_message(name, previous, current, info.milestone),
                )
            return

        if info.is_delivered:
            await archive_package(user_id, number)
            return

        if time.time() - sub["last_changed"] > STALE_DAYS * 86400:
            await archive_package(user_id, number)
            if sub["notifications_enabled"]:
                await self.notify_user(
                    user_id,
                    sub["notify_channel_id"],
                    f"🗄️ {name} hasn't had an update in {STALE_DAYS} days, so I've stopped "
                    "tracking it. Use `/track` to start again.",
                )

    @tasks.loop(minutes=POLL_MINUTES)
    async def check_package_updates(self):
        try:
            subscriptions = await get_active_subscriptions()

            # One API call per unique tracking number, however many users track it.
            by_number = defaultdict(list)
            for sub in subscriptions:
                by_number[sub["tracking_number"]].append(sub)

            semaphore = asyncio.Semaphore(MAX_CONCURRENT_LOOKUPS)

            async def process(number, subs):
                async with semaphore:
                    try:
                        info = await track_package(number)
                    except Exception:
                        logger.exception("Failed to check package %s", number)
                        return

                for sub in subs:
                    try:
                        await self.process_subscription(sub, info)
                    except Exception:
                        logger.exception(
                            "Failed to process package %s for user %s",
                            number,
                            sub["user_id"]
                        )

            await asyncio.gather(*(process(n, s) for n, s in by_number.items()))

            pruned = await prune_archived()
            if pruned:
                logger.info("Pruned %s old archived package(s).", pruned)
        except Exception:
            # Keep the loop alive no matter what.
            logger.exception("Package update check failed.")

    @check_package_updates.before_loop
    async def before_package_updates(self):
        await self.wait_until_ready()

    @tasks.loop(minutes=10)
    async def housekeeping(self):
        prune_rate_limits()


client = MyClient()


# ---------- Views ----------

class OwnedView(discord.ui.View):
    """A view only its owner can use; every interaction counts toward the 'other action' limit."""

    def __init__(self, user_id: int):
        super().__init__(timeout=180)
        self.user_id = user_id
        self.message = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message(
                "Only the person who ran this command can use these controls.",
                ephemeral=True
            )
            return False

        if await reject_if_rate_limited(interaction, "other"):
            return False

        return True

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True
        if self.message is not None:
            try:
                await self.message.edit(view=self)
            except discord.HTTPException:
                pass


class SettingsView(OwnedView):
    def __init__(self, user_id: int, settings: dict, in_guild: bool):
        super().__init__(user_id)
        self.settings = settings
        if not in_guild:
            self.remove_item(self.pick_channel)
        self.refresh_buttons()

    def refresh_buttons(self):
        self.toggle_visibility.label = (
            "Make responses private"
            if self.settings["public_responses"]
            else "Make responses public"
        )
        self.toggle_notifications.label = (
            "Mute notifications"
            if self.settings["notifications_enabled"]
            else "Unmute notifications"
        )
        self.use_dms.disabled = not self.settings["notify_channel_id"]

    async def save(self, interaction: discord.Interaction, name: str, value):
        self.settings[name] = value
        await set_setting(str(self.user_id), name, value)
        self.refresh_buttons()
        await interaction.response.edit_message(
            content=settings_text(self.settings),
            view=self
        )

    @discord.ui.button(label="Make responses private", style=discord.ButtonStyle.primary, row=0)
    async def toggle_visibility(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.save(interaction, "public_responses", not self.settings["public_responses"])

    @discord.ui.button(label="Mute notifications", style=discord.ButtonStyle.secondary, row=0)
    async def toggle_notifications(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.save(
            interaction,
            "notifications_enabled",
            not self.settings["notifications_enabled"]
        )

    @discord.ui.button(label="Use DMs for updates", style=discord.ButtonStyle.secondary, row=0)
    async def use_dms(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.save(interaction, "notify_channel_id", None)

    @discord.ui.select(
        cls=discord.ui.ChannelSelect,
        channel_types=[discord.ChannelType.text],
        placeholder="Send updates to a server channel…",
        min_values=1,
        max_values=1,
        row=1,
    )
    async def pick_channel(self, interaction: discord.Interaction, select: discord.ui.ChannelSelect):
        channel = interaction.guild.get_channel(select.values[0].id) if interaction.guild else None
        me = interaction.guild.me if interaction.guild else None

        if channel is None or me is None:
            await interaction.response.send_message(
                "I couldn't look up that channel. Please try another one.",
                ephemeral=True
            )
            return

        bot_perms = channel.permissions_for(me)
        user_perms = channel.permissions_for(interaction.user)

        if not (bot_perms.view_channel and bot_perms.send_messages):
            await interaction.response.send_message(
                f"I don't have permission to post in {channel.mention}.",
                ephemeral=True
            )
            return

        if not (user_perms.view_channel and user_perms.send_messages):
            await interaction.response.send_message(
                f"You can't post in {channel.mention} yourself, so I can't send your updates there.",
                ephemeral=True
            )
            return

        await self.save(interaction, "notify_channel_id", str(channel.id))


class PackageView(OwnedView):
    def __init__(
        self,
        user_id: int,
        info: TrackingInfo,
        label: Optional[str] = None,
        tracked: bool = False
    ):
        super().__init__(user_id)
        self.info = info
        self.label = label

        self.add_item(discord.ui.Button(
            label="Open tracking page",
            url=tracking_url(info.tracking_number),
        ))

        if tracked:
            self.remove_item(self.track_button)

    @discord.ui.button(label="📜 History", style=discord.ButtonStyle.secondary)
    async def show_history(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(
            embed=build_history_embed(self.info, self.label),
            ephemeral=await ephemeral_for(self.user_id)
        )

    @discord.ui.button(label="➕ Track this package", style=discord.ButtonStyle.success)
    async def track_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        result, _ = await add_package(
            str(self.user_id),
            self.info.tracking_number,
            self.info.carrier,
            self.info.status_text,
            self.label,
            archived=self.info.is_delivered,
        )

        if result == "limit":
            await interaction.response.send_message(limit_message(), ephemeral=True)
            return

        self.remove_item(self.track_button)
        await interaction.response.edit_message(view=self)
        await interaction.followup.send(
            "✅ Now tracking this package. I'll notify you when the status changes.",
            ephemeral=True
        )


# ---------- Autocomplete ----------

def make_package_autocomplete(predicate: Optional[Callable[[dict], bool]] = None):
    async def autocomplete(interaction: discord.Interaction, current: str):
        packages = await get_packages(str(interaction.user.id))
        current = current.lower()
        choices = []

        for package in packages:
            if predicate and not predicate(package):
                continue

            haystack = (
                f"{package['tracking_number']} "
                f"{package['label'] or ''} {package['carrier'] or ''}"
            ).lower()
            if current not in haystack:
                continue

            title = package["label"] or package["carrier"] or "Package"
            choices.append(app_commands.Choice(
                name=f"{title} - {package['tracking_number']}"[:100],
                value=package["tracking_number"],
            ))

        return choices[:25]

    return autocomplete


# ---------- Command helpers ----------

async def report_tracking_failure(
    interaction: discord.Interaction,
    exc: Exception,
    tracking_number: str
):
    if isinstance(exc, TrackingError):
        message = exc.user_message
    else:
        # Keep internal error details in the server logs, not Discord.
        logger.error(
            "Unexpected failure for user %s and tracking number %s",
            interaction.user.id,
            tracking_number,
            exc_info=exc
        )
        message = TrackingError.user_message

    await interaction.followup.send(message, ephemeral=True)


# ---------- Commands ----------

@client.tree.command(
    name="track",
    description="Track a package and get notified when its status changes"
)
@app_commands.describe(
    tracking_number="The package's tracking number",
    label="Optional nickname, e.g. 'New headphones'"
)
async def track(
    interaction: discord.Interaction,
    tracking_number: str,
    label: Optional[app_commands.Range[str, 1, 50]] = None
):
    if await reject_if_rate_limited(interaction, "command"):
        return

    ephemeral = await ephemeral_for(interaction.user.id)
    await interaction.response.defer(ephemeral=ephemeral)

    try:
        tracking_number = normalize_tracking_number(tracking_number)
        info = await track_package(tracking_number)
        result, saved_label = await add_package(
            str(interaction.user.id),
            tracking_number,
            info.carrier,
            info.status_text,
            label,
            archived=info.is_delivered,
        )
    except Exception as exc:
        await report_tracking_failure(interaction, exc, tracking_number)
        return

    if result == "limit":
        await interaction.followup.send(limit_message(), ephemeral=True)
        return

    if info.is_delivered:
        note = "✅ This package has already been delivered, so I won't keep checking it."
    else:
        note = "✅ Now tracking this package. I'll notify you when the status changes."

    view = PackageView(interaction.user.id, info, saved_label, tracked=True)
    view.message = await interaction.followup.send(
        content=note,
        embed=build_tracking_embed(info, saved_label),
        view=view,
        ephemeral=ephemeral
    )


@client.tree.command(
    name="lookup",
    description="Check a package once without tracking it"
)
@app_commands.describe(tracking_number="The package's tracking number")
async def lookup(interaction: discord.Interaction, tracking_number: str):
    if await reject_if_rate_limited(interaction, "command"):
        return

    ephemeral = await ephemeral_for(interaction.user.id)
    await interaction.response.defer(ephemeral=ephemeral)

    try:
        tracking_number = normalize_tracking_number(tracking_number)
        info = await track_package(tracking_number)
        existing = await get_package(str(interaction.user.id), tracking_number)
    except Exception as exc:
        await report_tracking_failure(interaction, exc, tracking_number)
        return

    label = existing["label"] if existing else None
    already_tracked = existing is not None and not existing["archived"]

    view = PackageView(interaction.user.id, info, label, tracked=already_tracked)
    view.message = await interaction.followup.send(
        embed=build_tracking_embed(info, label),
        view=view,
        ephemeral=ephemeral
    )


@client.tree.command(
    name="history",
    description="Show the recent tracking events for a package"
)
@app_commands.describe(tracking_number="Pick one of your packages or type a tracking number")
async def history(interaction: discord.Interaction, tracking_number: str):
    if await reject_if_rate_limited(interaction, "command"):
        return

    ephemeral = await ephemeral_for(interaction.user.id)
    await interaction.response.defer(ephemeral=ephemeral)

    try:
        tracking_number = normalize_tracking_number(tracking_number)
        info = await track_package(tracking_number)
        existing = await get_package(str(interaction.user.id), tracking_number)
    except Exception as exc:
        await report_tracking_failure(interaction, exc, tracking_number)
        return

    await interaction.followup.send(
        embed=build_history_embed(info, existing["label"] if existing else None),
        ephemeral=ephemeral
    )


@client.tree.command(
    name="mytracks",
    description="Show all of your tracked packages"
)
async def mytracks(interaction: discord.Interaction):
    if await reject_if_rate_limited(interaction, "command"):
        return

    user_id = str(interaction.user.id)
    ephemeral = await ephemeral_for(interaction.user.id)
    packages = await get_packages(user_id)

    if not packages:
        await interaction.response.send_message(
            "📦 You aren't tracking any packages yet.",
            ephemeral=ephemeral
        )
        return

    active_count = sum(1 for p in packages if not p["archived"])
    embed = discord.Embed(title="📦 Your Packages")

    for package in packages[:25]:
        status = package["status"] or "Unknown"
        details = [package["carrier"] or "Unknown", f"**{status}**"]
        if package["paused"]:
            details.append("⏸️ paused")
        if package["archived"]:
            details.append("🗄️ archived")

        embed.add_field(
            name=f"{status_emoji(status)} {package['label'] or package['carrier'] or 'Package'}",
            value=f"`{package['tracking_number']}`\n{' · '.join(details)}",
            inline=False
        )

    footer = f"{active_count}/{MAX_ACTIVE_PACKAGES_PER_USER} active packages"
    if len(packages) > 25:
        footer += f" · showing 25 of {len(packages)}"
    embed.set_footer(text=footer)

    await interaction.response.send_message(embed=embed, ephemeral=ephemeral)


@client.tree.command(
    name="untrack",
    description="Stop tracking a package"
)
@app_commands.describe(tracking_number="Pick one of your packages")
async def untrack(interaction: discord.Interaction, tracking_number: str):
    if await reject_if_rate_limited(interaction, "command"):
        return

    ephemeral = await ephemeral_for(interaction.user.id)
    tracking_number = tracking_number.strip().replace(" ", "")
    removed = await remove_package(str(interaction.user.id), tracking_number)

    if removed:
        message = f"✅ Stopped tracking `{tracking_number}`."
    else:
        message = f"❌ I couldn't find `{tracking_number}` in your tracked packages."

    await interaction.response.send_message(message, ephemeral=ephemeral)


@client.tree.command(
    name="pause",
    description="Temporarily stop notifications for a package"
)
@app_commands.describe(tracking_number="Pick one of your packages")
async def pause(interaction: discord.Interaction, tracking_number: str):
    if await reject_if_rate_limited(interaction, "command"):
        return

    ephemeral = await ephemeral_for(interaction.user.id)
    tracking_number = tracking_number.strip().replace(" ", "")
    changed = await set_paused(str(interaction.user.id), tracking_number, True)

    if changed:
        message = f"⏸️ Paused `{tracking_number}`. Use `/resume` to start checking it again."
    else:
        message = f"❌ I couldn't find an active package `{tracking_number}`."

    await interaction.response.send_message(message, ephemeral=ephemeral)


@client.tree.command(
    name="resume",
    description="Resume notifications for a paused package"
)
@app_commands.describe(tracking_number="Pick one of your paused packages")
async def resume(interaction: discord.Interaction, tracking_number: str):
    if await reject_if_rate_limited(interaction, "command"):
        return

    ephemeral = await ephemeral_for(interaction.user.id)
    tracking_number = tracking_number.strip().replace(" ", "")
    changed = await set_paused(str(interaction.user.id), tracking_number, False)

    if changed:
        message = f"▶️ Resumed `{tracking_number}`."
    else:
        message = f"❌ I couldn't find an active package `{tracking_number}`."

    await interaction.response.send_message(message, ephemeral=ephemeral)


@client.tree.command(
    name="settings",
    description="Configure responses, notifications and where updates are sent"
)
async def settings(interaction: discord.Interaction):
    if await reject_if_rate_limited(interaction, "command"):
        return

    user_settings = await get_settings(str(interaction.user.id))
    view = SettingsView(interaction.user.id, user_settings, in_guild=interaction.guild is not None)

    await interaction.response.send_message(
        settings_text(user_settings),
        view=view,
        ephemeral=True
    )
    view.message = await interaction.original_response()


untrack.autocomplete("tracking_number")(make_package_autocomplete())
history.autocomplete("tracking_number")(make_package_autocomplete())
pause.autocomplete("tracking_number")(
    make_package_autocomplete(lambda p: not p["paused"] and not p["archived"])
)
resume.autocomplete("tracking_number")(
    make_package_autocomplete(lambda p: bool(p["paused"]) and not p["archived"])
)


@client.tree.error
async def on_app_command_error(
    interaction: discord.Interaction,
    error: app_commands.AppCommandError
):
    logger.error("Unhandled command error", exc_info=error)
    message = "❌ Something went wrong. Please try again."

    try:
        if interaction.response.is_done():
            await interaction.followup.send(message, ephemeral=True)
        else:
            await interaction.response.send_message(message, ephemeral=True)
    except discord.HTTPException:
        pass


if __name__ == "__main__":
    if not DISCORD_TOKEN:
        raise SystemExit("DISCORD_TOKEN is not set. Add it to your .env file.")
    client.run(DISCORD_TOKEN)