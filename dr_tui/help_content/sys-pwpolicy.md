# View and Manage the Password and

*Source: Add or Edit a System User - Unknown.pdf*

View and Manage the Password and
User Logout Policy
Home > Settings drop-down > System Settings >
Configuration > Password & User Logout Policy
Project > Settings drop-down > System Setting >
Configuration > Password & User Logout Policy

Requires System-level Password & User Logout Policy View permissions to view the Password & User Logout
Policy information, Add/Edit permissions to edit the
information
Note: The eDiscovery Password Policy applies only to systems
explicitly configured for Standard Authentication. Systems configured
for TransPerfect Authentication (the default) uphold the TransPerfect
Authentication password policy. Both forms of authentication do
observe the User Logout Policy.
By default, all System roles can view the Password & User Logout
Policy information. System Users in a System-level role with the
appropriate permissions on a Standard Authentication system can
enforce when eDiscovery users have to change their password, as
well as set password policy (that is, the strength of passwords based
on the password requirements). By default, only a System User in
the System Administrator role has permissions to manage the
Password & User Logout Policy information. For information about
System-level permissions, see View and Manage System Role-Based
Permissions.
Note: Changes in password policy apply to new users and existing
users when they change their password on a Standard
Authentication system.

Upon login, users on a Standard Authentication system can click
Change Password to change their password if they need to
change their password.
When the password of a System User or Organization User expires,
that user will be required to make a password change at the next
login to eDiscovery. Any password change is logged as an event in
the system Status Log. Note that newly created System or
Organization Users, or System or Organization Users whose
passwords have been reset by an Administrator must also change
their passwords before they can log in to eDiscovery.

Password Policy that Applies to
TransPerfect Authentication
Note: This section applies only to a system configured for
TransPerfect Authentication.
This section will display the current password policy in effect for
TransPerfect Authentication. The policy is enforced for new User
entries being created in eDiscovery for TP Auth, and for newly added
TP Auth Users who need to change their password upon initial login
using their TP Auth credentials. This policy can change based on TP
Auth password policy requirements. Note that this password policy
information is view-only on this screen, as it is controlled by
TransPerfect.

Password Policy Options for Standard
Authentication
Note: This section does not apply to a system configured for
TransPerfect Authentication.
Password expires <value> days since change/reset —
Use the default of 90 days, or specify the number of days you
want to use for the password expiration policy. The maximum
value is 9999. The minimum value is 1.
Enable the password strength rules below — Use this
checkbox to set a strict password strength policy for users (a
strong password Closed A strong password minimally has the
following: at least 8 characters uppercase and lowercase letters
a number a non-alphanumeric symbol. A user with System
Administrator permissions can configure the minimum
requirements for user passwords as a password policy. ). When
this checkbox is selected, you can also configure what the
requirements are for passwords (keeping in mind that
eDiscovery Users will be subject to these restrictions after they
are applied):
Note: The following fields, when enabled, cannot be blank. If
you make them blank and attempt to proceed, a tooltip will
remind you that the field cannot be blank and that the current
setting value has been entered.
Minimum password length — Sets the minimum
number of characters required for a valid password (for
example, 10 characters, perhaps with 2 uppercase letters, 5
lowercase letters, 2 numbers, and one symbol). When
selecting a minimum number of characters for eDiscovery
User passwords, be aware that the maximum number of
characters supported is effectively 64 for locally

authenticated passwords. Therefore, do not attempt to set
this minimum length value too high. The range is 0-99.
Selecting the minimum value of 0 effectively means there is
no password length enforced, which is not recommended.
The default is 6.
Minimum uppercase letters — Sets the minimum
number of uppercase letters (A-Z) required for a valid
password. The valid range is 0 - 99 (0 is the initial default).
Minimum lowercase letters — Sets the minimum
number of lowercase letters (a-z) required for a valid
password. The valid range is 0 - 99 (0 is the initial default).
Minimum numbers — Sets the minimum number of
numeric characters (0-9) required for a valid password. The
valid range is 0 - 99 (0 is the initial default).
Minimum symbols — Sets the minimum number of
symbols required for a valid password. The valid range is 0
- 99 (0 is the initial default). The software considers
anything other than alphanumeric characters a symbol,
including the following:
_-!"#$%&*+./:;<=>?@[\]^{|}~

User Session Settings (Logout Policy)
This setting governs the logout policy used for all user logins to
eDiscovery. When the logout timeout is reached after the specified
number of minutes of inactivity, a user will be logged out when
attempting to resume activity. That user will then have to log back in
to resume activity.
Log user out after <value> minutes of inactivity — Use
the default value of 20, or specify the number of minutes you
want to use for the timeout. The valid range is 1-99 minutes.

Password Policy & User Logout Settings:
Save or Discard Changes Options
If you do not save your changes before navigating away, you will be
prompted to either save your changes and continue navigating away,
discard your changes and continue navigating away, or cancel your
changes and remain in the current location.
Save – Saves your changes to the Password Policy options
and/or User Logout setting.
Discard Changes – Discards your changes to the Password
Policy options and/or User Logout setting.
