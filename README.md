# 📦 Package Tracker Bot

Track your packages directly from Discord with the help of Ship24.

## 🤖 Add the Bot to Your Server

**[Invite Package Tracker Bot](https://discord.com/oauth2/authorize?client_id=1543461664953991179&permissions=2048&integration_type=0&scope=bot+applications.commands)**

To invite the bot:

1.  Open the invite link above.
2.  Sign in to Discord if prompted.
3.  Choose the server where you want to add the bot.
4.  Make sure you have permission to manage or add apps to that server.
5.  Review the requested permissions and click **Authorize**.
6.  Open your server and use the bot's slash commands.

> **Invite link setup:** Replace `YOUR_DISCORD_INVITE_LINK_HERE` with
> your bot's authorization URL. You can generate one in the [Discord
> Developer Portal](https://discord.com/developers/applications): select
> your application, open **OAuth2 → URL Generator**, select the `bot`
> and `applications.commands` scopes, choose only the permissions the
> bot needs, and copy the generated URL.

## ✨ What Does It Do?

Package Tracker Bot helps you check and monitor shipment progress
without leaving Discord.

-   **Track a package:** Submit a tracking number to retrieve shipment
    information through Ship24.
-   **View tracked packages:** See the packages associated with your
    Discord account.
-   **Get status notifications:** The bot checks tracked packages
    periodically and can DM you when a shipment status changes.
-   **Manage tracking:** Stop tracking a package when you no longer need
    updates.
-   **Choose response visibility:** Configure whether command responses
    should be public or private.

Shipment details, carrier coverage, and update timing depend on Ship24
and the shipping carrier. Tracking information may be delayed,
incomplete, or unavailable.

## 💬 Commands

  -----------------------------------------------------------------------
  Command                             What it does
  ----------------------------------- -----------------------------------
  `/track`                            Look up a tracking number and add
                                      the package to your tracked list.

  `/mytracks`                         Open your list of tracked packages.

  `/untrack`                          Stop tracking a package by its
                                      tracking number.

  `/settings`                         Change your response visibility
                                      preference.
  -----------------------------------------------------------------------

The bot may ask for additional information when you use a command.
Follow the prompts shown in Discord.

## 🔔 Notifications

The bot checks saved packages periodically (configured for every 15
minutes) and attempts to send a direct message when a package's status
changes.

To receive notifications:

-   Allow direct messages from the bot where your Discord privacy
    settings permit it.
-   Keep in mind that notifications depend on the bot being online and
    Ship24 returning updated tracking information.
-   If a DM cannot be delivered or a carrier has not reported a new
    event, you may not receive an update.

## 🔒 Privacy

The bot stores information needed to provide tracking, including your
Discord user ID, tracking number, carrier, shipment status, and
response-visibility preference. Tracking numbers are sent to Ship24 to
retrieve shipment information.

Use `/untrack` to stop monitoring a package through the bot. This may
not delete all account preferences or information retained by
third-party providers.

Read the project's [Privacy Policy](PRIVACY.md) and [Terms of
Service](TERMS.md) for more information.

## ❓ Troubleshooting

-   **Commands do not appear:** Global slash commands may take time to
    become available after the bot is added. Try restarting Discord or
    waiting a little while.
-   **The bot does not respond:** Check that it is online and that the
    server has authorized the requested app permissions.
-   **No DM notifications:** Check your Discord DM/privacy settings and
    remember that status updates depend on the carrier and Ship24.
-   **Tracking lookup fails:** Verify the tracking number and try again
    later. Some carriers or shipments may not have available tracking
    data.

## 📬 Contact

**Operator:** Johnnytan\
**Discord:** `@johnny_tans`

For questions, feedback, or support, contact the operator on Discord.

## ⚠️ Disclaimer

This is an independently operated bot and is not affiliated with
Discord, Ship24, or any shipping carrier. The bot relies on third-party
services and does not guarantee shipment accuracy, delivery dates,
uninterrupted availability, or successful notifications.
