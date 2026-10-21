# Privacy Policy — Package Tracker Bot

**Effective date:** October 20, 2026  
**Last updated:** October 20, 2026

## 1. Who operates this bot

This Privacy Policy applies to Package Tracker Bot ("the Bot"), a Discord application that retrieves shipment information and provides package-tracking notifications.

The Bot is operated by **Johnnytan** ("the operator," "I," or "we").

**Contact:** `@johnny_tans` on Discord.

This policy explains what information the Bot processes, why it is processed, which services receive it, how long it is retained, and how users can request deletion.

## 2. Information the Bot processes

When you use the Bot, it processes the following information:

- **Discord user ID:** Identifies the account associated with a tracked package and user preferences.
- **Tracking number:** Allows the Bot to request shipment information and monitor delivery progress.
- **Carrier information:** Identifies the shipping carrier when available.
- **Shipment status:** Records the latest status used to detect changes and send notifications.
- **Response-visibility preference:** Records whether supported command responses should be public or private.
- **Command and interaction information:** Discord processes the interactions you submit. The Bot uses information necessary to execute commands and associate results with your account.

The Bot does not intentionally request your Discord password, payment information, or access to private conversations unrelated to its functions.

Tracking numbers can reveal shipment details about you or another person. Only submit a tracking number that you are authorized to use.

## 3. How information is used

The Bot processes information to:

- Retrieve tracking information from Ship24.
- Associate packages with the user who added them.
- Display package information through Discord.
- Periodically check tracked packages for status changes.
- Send direct-message notifications about detected changes.
- Save response-visibility preferences.
- Enforce basic usage limits, troubleshoot errors, and maintain the service.

The Bot is not intended to sell personal information or use tracking information for advertising.

## 4. How information is shared

Information may be processed by the following service providers:

**Discord:** Processes commands, user identifiers, and messages or responses delivered through its platform.

**Ship24:** Receives submitted tracking numbers through the Bot's tracking API and provides shipment information. Ship24 may process those numbers and related request data under its own terms and privacy practices.

**CogitHost:** Hosts the Bot. Its infrastructure may process server files, configuration information, technical logs, and other information as described in its policies and hosting terms.

The operator does not control the independent data practices of these providers. Information may also be disclosed when required by law or when reasonably necessary to address security, abuse, or legal obligations.

The operator does not intentionally sell or rent users' personal information.

## 5. Public and private responses

The Bot supports a preference for public or private command responses.

Public responses may be visible to other members of a Discord server. Private interaction responses are intended to be visible only to the requesting user, subject to Discord's platform behavior and policies.

This preference does not guarantee that every interaction, notification, or piece of information is private. Automatic package notifications are sent through Discord direct messages. Their delivery depends on Discord and the recipient's settings.

Users should avoid posting tracking numbers publicly if they do not want other server members to see them.

## 6. Storage and security

The Bot stores tracked-package records and response-visibility preferences in a SQLite database on its hosting environment.

The operator takes reasonable steps appropriate to this project to restrict access to credentials and stored information. However, no online service or storage system can be guaranteed completely secure.

The Bot depends on Discord, Ship24, CogitHost, and other underlying infrastructure. Their systems may have separate logs, backups, and retention practices.

Users should not treat the Bot as a secure document vault or submit information that is unnecessary for package tracking.

## 7. Retention and deletion

Tracked package records are retained while they are being tracked. The Bot's `/untrack` command removes the selected package record from its database.

Removing a package does not, by itself, delete the user's response-visibility preference or information independently retained by Discord, Ship24, or CogitHost.

To request deletion of information associated with your Discord user ID, contact **@johnny_tans on Discord**. Include your Discord user ID if necessary to identify the relevant records. Do not send your password, bot credentials, or other secrets.

The operator will review and respond to deletion requests and delete applicable information promptly when required by law or applicable platform terms, subject to any lawful retention obligations. Information in provider-controlled systems or backups may be subject to separate deletion and retention procedures.

If the Bot is discontinued, the operator will handle stored Discord API data in accordance with applicable law and Discord's Developer Terms, including applicable deletion requirements.

## 8. Children's privacy

The Bot is not specifically directed at children. Users must satisfy Discord's minimum age requirements and any additional age requirements imposed by applicable law.

## 9. Changes to this policy

This policy may be updated when the Bot's functionality, data practices, or legal requirements change. The current version will be published at the designated policy URL with an updated date.

Material changes will be reflected in the policy. Users should review it periodically.

## 10. Contact

For privacy questions, concerns, or deletion requests, contact:

**Operator:** Johnnytan  
**Discord contact:** @johnny_tans

