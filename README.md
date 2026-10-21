# 📦 Package Tracker Bot

Track your packages directly from Discord with the help of Ship24.

## 🤖 Add the Bot to Your Server

**[Invite Package Tracker Bot](https://discord.com/oauth2/authorize?client_id=1543461664953991179&permissions=2048&integration_type=0&scope=bot+applications.commands)**

To invite the bot:

1. Open the invite link above.
2. Sign in to Discord if prompted.
3. Choose the server where you want to add the bot.
4. Make sure you have permission to manage or add apps to that server.
5. Review the requested permissions and click **Authorize**.
6. Open your server and use the bot's slash commands.

## ✨ What Does It Do?

Package Tracker Bot helps you check and monitor shipment progress without leaving Discord.

- **Track a package:** Submit a tracking number to retrieve shipment information through Ship24.
- **View tracked packages:** See the packages associated with your Discord account.
- **Get status notifications:** The bot checks tracked packages periodically and can DM you when a shipment status changes.
- **Manage tracking:** Stop tracking a package when you no longer need updates.
- **Choose response visibility:** Configure whether command responses should be public or private.

Shipment details, carrier coverage, and update timing depend on Ship24 and the shipping carrier. Tracking information may be delayed, incomplete, or unavailable.

## 🚚 Supported Couriers

Package Tracker Bot uses **Ship24** to retrieve shipment tracking information. Ship24 supports more than 2,500 couriers worldwide, including postal services, express delivery companies, regional carriers, and specialized logistics providers.

### Examples of supported couriers

The following are examples of carriers available through Ship24, not an exhaustive list.

| Courier | Region / Service |
|---|---|
| USPS | United States Postal Service |
| UPS | International parcel delivery |
| FedEx | International express delivery |
| DHL | International express and logistics |
| Royal Mail | United Kingdom postal service |
| China Post | Chinese postal service |
| Japan Post | Japanese postal service |
| Canada Post | Canadian postal service |
| Australia Post | Australian postal service |
| India Post | Indian postal service |
| La Poste / Colissimo | French postal and parcel delivery |
| DPD | European parcel delivery |
| GLS | European and international parcel delivery |
| Evri | United Kingdom parcel delivery |
| Purolator | Canadian courier service |
| Blue Dart | Indian courier and express delivery |
| DTDC | Indian courier service |
| Cainiao | E-commerce logistics |
| YunExpress | Cross-border e-commerce logistics |
| UniUni | North American last-mile delivery |
| OnTrac | United States parcel delivery |
| LaserShip | United States parcel delivery |
| SF Express | Chinese and international logistics |
| Aramex | International logistics and courier delivery |
| TNT | Express delivery and logistics |

### Find the complete courier list

For the most up-to-date list of supported couriers, consult Ship24's official resources:

- **[Ship24 Courier Directory](https://www.ship24.com/couriers)** — Browse individual courier tracking pages.
- **[Ship24 Courier API Documentation](https://docs.ship24.com/couriers)** — Learn how to retrieve the complete courier list and supported courier codes.
- **[Ship24 Tracking API Documentation](https://docs.ship24.com/)** — Learn more about Ship24's tracking service.

Ship24 also allows API users to retrieve the courier list through its `GET /couriers` endpoint. Account holders can download the courier list as a CSV file from the Ship24 dashboard.

**Important:** Ship24's overall courier coverage does not guarantee that every shipment will return tracking results. Availability depends on the carrier, tracking number, shipment details, and Ship24's current coverage. Some couriers also require additional information.

The bot relies on Ship24's tracking capabilities and does not independently integrate with every listed courier.

## 💬 Commands

| Command | What it does |
|---|---|
| `/track` | Look up a tracking number and add the package to your tracked list. |
| `/mytracks` | Open your list of tracked packages. |
| `/untrack` | Stop tracking a package by its tracking number. |
| `/settings` | Change your response visibility preference. |

The bot may ask for additional information when you use a command. Follow the prompts shown in Discord.

## 🔔 Notifications

The bot checks saved packages periodically, configured for every 15 minutes, and attempts to send a direct message when a package's status changes.

To receive notifications:

- Allow direct messages from the bot where your Discord privacy settings permit it.
- Keep in mind that notifications depend on the bot being online and Ship24 returning updated tracking information.
- If a DM cannot be delivered or a carrier has not reported a new event, you may not receive an update.

## 🔒 Privacy

The bot stores information needed to provide tracking, including your Discord user ID, tracking number, carrier, shipment status, and response-visibility preference. Tracking numbers are sent to Ship24 to retrieve shipment information.

Use `/untrack` to stop monitoring a package through the bot. This may not delete all account preferences or information retained by third-party providers.

Read the project's [Privacy Policy](PRIVACY.md) and [Terms of Service](TERMS.md) for more information.

## ❓ Troubleshooting

- **Commands do not appear:** Global slash commands may take time to become available after the bot is added. Try restarting Discord or waiting a little while.
- **The bot does not respond:** Check that it is online and that the server has authorized the requested app permissions.
- **No DM notifications:** Check your Discord DM/privacy settings and remember that status updates depend on the carrier and Ship24.
- **Tracking lookup fails:** Verify the tracking number and try again later. Some carriers or shipments may not have available tracking data.
- **Courier is not recognized:** Check the [Ship24 Courier Directory](https://www.ship24.com/couriers). Ship24 may automatically detect the carrier, but some shipments may require additional information or may not be supported for tracking.

## 📬 Contact

**Operator:** Johnnytan  
**Discord:** `@johnny_tans`

For questions, feedback, or support, contact the operator on Discord.

## ⚠️ Disclaimer

This is an independently operated bot and is not affiliated with Discord, Ship24, or any shipping carrier. The bot relies on third-party services and does not guarantee shipment accuracy, delivery dates, uninterrupted availability, or successful notifications.
