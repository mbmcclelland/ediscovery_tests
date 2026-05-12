# View and Request Virus Detection

*Source: View and Request Virus Detectio - Unknown.pdf*

View and Request Virus Detection
Updates
Home > Settings drop-down > System Settings >
Configuration > Virus Detection
Project > Settings drop-down > System Setting >
Configuration > Virus Detection

Requires System-level Virus Detection - View permissions to
view the information, Add/Edit permissions to manage
updates
System Users in a role with the appropriate System-level permissions
can view information about Virus Detection updates and request an
update. By default, only a System Administrator has permissions to
manage Virus Detection updates. For information about System-level
permissions, see View and Manage System Role-Based Permissions.
Note: Virus Detection requires prior selection of a System Storage
Depot. No updates can occur until the System Storage Depot has
been established. Once the system storage for the System Storage
Depot has been selected and the Depot is established, updates are
enabled automatically to ensure that the latest Virus definitions (the
files used to identify specific viruses) are picked up on a daily basis
at 2 am. You can also request an update once the System Storage
Depot has been configured (for example, if you want to pick up the
latest definitions immediately because the daily update has not
occurred yet).
To ensure that the same Virus Detection version is used throughout
a given system, Virus Detection updates (the updated virus
definitions) are distributed from the Service Node to all nodes in the
system.

If one or more email addresses are configured for Email Server &
Notifications, a Virus Detection Update failure will generate an email
notification with the subject Virus Detection Update Failed. The
email provides information (such as that an unexpected error
occurred while updating the Virus definition files).

Virus Detection Information and Update
Option
By default, Virus Detection is updated automatically every day at 2
am, as indicated by the displayed message, as long as a System
Storage Depot has been configured.
Current version: <version> — Displays the current version of
Virus Detection software on the system (for example, 26480). If
an update is in progress, you will see the icon with the
message Updating. This field shows N/A if no update has been
performed yet.
Update Now — Enables you to perform a Virus Detection
update on demand, which updates the current version, if an
update is needed.
Last updated — Displays the date and time of the last
successful Virus Detection update.
Status <message> —Reports the current status of the virus
update. This field shows N/A if no update has been performed
yet, or if no update is needed. While an update is in progress, a
status message indicates that an update is currently running. If
no System Storage Depot is established, you see a message to
notify your that the System Storage Depot must be defined
before updates can occur. (The message will then clear after
you establish the Depot.)
If an update fails, it could be because an unexpected error occurred
while updating the Virus definition files. You can try again at a later
time. If necessary, a System Administrator can verify that the Virus
Detection processes are running on all nodes properly.
