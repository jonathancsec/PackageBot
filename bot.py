import logging
import os
import time
from collections import defaultdict, deque
from math import ceil

import discord
from discord import app_commands
from discord.ext import tasks
from dotenv import load_dotenv

from tracker import track_package
from database import (
    initialize_database,
    add_package,
    get_packages,
    get_tracked_packages,
    remove_package,
    update_package_status,
    get_public_responses,
    set_public_responses
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
# Optional: used only to remove old server-specific command registrations.
GUILD_ID = os.getenv("GUILD_ID")


class MyClient(discord.Client):
    def __init__(self):
        intents = discord.Intents.default()
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self):
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

    @tasks.loop(minutes=15)
    async def check_package_updates(self):
        for _, user_id, tracking_number, previous_status in get_tracked_packages():
            try:
                result = await track_package(tracking_number)
                tracking = result["data"]["trackings"][0]
                current_status = (
                    tracking["shipment"]["statusMilestone"]
                    .replace("_", " ")
                    .title()
                )

                if current_status == previous_status:
                    continue

                user = await self.fetch_user(int(user_id))
                await user.send(
                    f"📦 Status update for `{tracking_number}`: "
                    f"**{previous_status}** → **{current_status}**"
                )
                update_package_status(user_id, tracking_number, current_status)
            except Exception:
                logger.exception(
                    "Failed to check or notify package %s for user %s",
                    tracking_number,
                    user_id
                )

    @check_package_updates.before_loop
    async def before_package_updates(self):
        await self.wait_until_ready()


client = MyClient()
initialize_database()

COMMAND_COOLDOWN_SECONDS = 5
OTHER_ACTION_LIMIT = 10
OTHER_ACTION_WINDOW_SECONDS = 60
last_command_requests = {}
other_action_requests = defaultdict(deque)


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


class SettingsView(discord.ui.View):
    def __init__(self, user_id: int, public_responses: bool):
        super().__init__(timeout=180)
        self.user_id = user_id
        self.public_responses = public_responses
        self.update_button()

    def update_button(self):
        self.toggle_visibility.label = (
            "Make responses private"
            if self.public_responses
            else "Make responses public"
        )

    @discord.ui.button(label="Make responses private", style=discord.ButtonStyle.primary)
    async def toggle_visibility(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message(
                "Only the person who opened these settings can change them.",
                ephemeral=True
            )
            return

        if await reject_if_rate_limited(interaction, "other"):
            return

        self.public_responses = not self.public_responses
        set_public_responses(str(self.user_id), self.public_responses)
        self.update_button()
        visibility = "public" if self.public_responses else "private"

        await interaction.response.edit_message(
            content=f"Your command responses are currently **{visibility}**.",
            view=self
        )


class MyTracksView(discord.ui.View):
    def __init__(self, user_id: int):
        super().__init__(timeout=180)
        self.user_id = user_id

    @discord.ui.button(label="View my tracks", style=discord.ButtonStyle.primary)
    async def view_tracks(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message(
                "Only the person who requested this list can view it.",
                ephemeral=True
            )
            return

        if await reject_if_rate_limited(interaction, "other"):
            return

        packages = get_packages(str(self.user_id))

        if not packages:
            await interaction.response.edit_message(
                content="📦 You aren't tracking any packages yet.",
                view=None
            )
            return

        embed = discord.Embed(
            title="📦 Your Packages",
            description="Packages you're currently tracking:"
        )

        for tracking_number, carrier, status in packages:
            embed.add_field(
                name=f"🚚 {carrier}",
                value=f"`{tracking_number}`\nStatus: **{status}**",
                inline=False
            )

        await interaction.response.edit_message(
            content=None,
            embed=embed,
            view=None
        )


@client.tree.command(
    name="track",
    description="Track a package"
)
async def track(
    interaction: discord.Interaction,
    tracking_number: str
):
    if await reject_if_rate_limited(interaction, "command"):
        return

    public_responses = get_public_responses(str(interaction.user.id))
    await interaction.response.defer(ephemeral=not public_responses)

    try:
        result = await track_package(tracking_number)

        tracking = result["data"]["trackings"][0]

        shipment = tracking["shipment"]
        events = tracking["events"]

        status = shipment["statusMilestone"]

        if events:
            carrier = events[0]["courierCode"].upper()
        else:
            carrier = "Unknown"

        if events:
            latest_event = events[0]
            event_status = latest_event["status"]
            location = latest_event["location"] or "Unknown"
            update_time = latest_event["occurrenceDatetime"]
        else:
            event_status = "No events yet"
            location = "Unknown"
            update_time = "Unknown"

        estimated_delivery = shipment["delivery"]["estimatedDeliveryDate"]

        if estimated_delivery:
            delivery_text = estimated_delivery
        else:
            delivery_text = "Not available"

        status_text = status.replace("_", " ").title()

        # Save package to database
        add_package(
            str(interaction.user.id),
            tracking_number,
            carrier,
            status_text
        )

        embed = discord.Embed(
            title="📦 Package Tracking",
            description=f"`{tracking_number}`"
        )

        embed.add_field(
            name="🚚 Carrier",
            value=carrier,
            inline=True
        )

        embed.add_field(
            name="📊 Status",
            value=status_text,
            inline=True
        )

        embed.add_field(
            name="📍 Location",
            value=location,
            inline=True
        )

        embed.add_field(
            name="📝 Latest Update",
            value=event_status,
            inline=False
        )

        embed.add_field(
            name="🕐 Last Updated",
            value=update_time,
            inline=True
        )

        embed.add_field(
            name="📅 Estimated Delivery",
            value=delivery_text,
            inline=True
        )

        embed.set_footer(
            text="Tracking information provided by Ship24"
        )

        await interaction.followup.send(
            embed=embed,
            view=MyTracksView(interaction.user.id),
            ephemeral=not public_responses
        )

    except Exception:
        # Keep API, database, and internal error details in server logs, not Discord.
        logger.exception(
            "Package tracking failed for user %s and tracking number %s",
            interaction.user.id,
            tracking_number
        )
        await interaction.followup.send(
            "❌ I couldn't retrieve tracking information right now. "
            "Please check the tracking number and try again later.",
            ephemeral=True
        )


@client.tree.command(
    name="settings",
    description="Configure your bot response settings"
)
async def settings(interaction: discord.Interaction):
    if await reject_if_rate_limited(interaction, "command"):
        return

    public_responses = get_public_responses(str(interaction.user.id))
    visibility = "public" if public_responses else "private"

    await interaction.response.send_message(
        f"Your command responses are currently **{visibility}**.",
        view=SettingsView(interaction.user.id, public_responses),
        ephemeral=True
    )


@client.tree.command(
    name="mytracks",
    description="Show your tracked packages"
)
async def mytracks(
    interaction: discord.Interaction
):
    if await reject_if_rate_limited(interaction, "command"):
        return

    packages = get_packages(str(interaction.user.id))

    if not packages:
        await interaction.response.send_message(
            "📦 You aren't tracking any packages yet.",
            ephemeral=not get_public_responses(str(interaction.user.id))
        )
        return

    await interaction.response.send_message(
        "Click below to view your tracked packages.",
        view=MyTracksView(interaction.user.id),
        ephemeral=not get_public_responses(str(interaction.user.id))
    )

@client.tree.command(
    name="untrack",
    description="Stop tracking a package"
)
async def untrack(
    interaction: discord.Interaction,
    tracking_number: str
):
    if await reject_if_rate_limited(interaction, "command"):
        return

    public_responses = get_public_responses(str(interaction.user.id))
    removed = remove_package(
        str(interaction.user.id),
        tracking_number
    )

    if removed:
        await interaction.response.send_message(
            f"✅ Stopped tracking `{tracking_number}`.",
            ephemeral=not public_responses
        )
    else:
        await interaction.response.send_message(
            f"❌ I couldn't find `{tracking_number}` in your tracked packages.",
            ephemeral=not public_responses
        )

client.run(DISCORD_TOKEN)