# Add or Edit a System User

*Source: Add or Edit a System User - Unknown.pdf*

Add or Edit a System User
Home >Settings drop-down > System Settings >
Provisioning > System Users > New System User |
Edit
Project > Settings drop-down> System Settings >
Provisioning > System Users > New System User |
Edit
Home > Settings drop-down > System Settings >
Provisioning > System Users > Retry TP Auth Setup

Requires System Users - Add/Edit permissions
If you have the appropriate System-level permissions, you can add a
new System User entry or edit the information for an existing User
entry.
Note: From the System Users screen, you can use Add to /
Remove from Organizations to select the member Organizations
for a given System User.

Supported Authentication Types
All User entries on a system are created based on the primary
authentication method configured for the system, as follows:
TransPerfect Authentication (default) — Also known as
TP Auth, this method requires setup and management of a
corporate-assigned email address and password for a System
User. A User entry created in eDiscovery using TP Auth requires
an email address for the User to receive emails from the
software, but the User entry itself does not include a username,
nor does it enable specification of a password if the User is
already defined in TP Auth. (For TP Auth, the corporateassigned email address is effectively serving as a username.) TP
Auth can be used with or without Authorized IP addresses.
Standard Authentication (must be explicitly set for a system)
— The legacy authentication method, which minimally requires
configuration of a username, password, and email address, and
can also support one or more additional authentication
methods.
The following summarizes the additional authentication methods
available depending on the primary authentication type set for a
system:
Password — This base authentication is always enabled and a
password is always required, regardless of the type of
authentication configured.
Email Security Code (Standard Authentication systems only)
— This provides email -based Multi-Factor Authentication (MFA)
for a Standard Authentication User. It requires availability of a
Mail Server on the system to deliver a 6-digit code to the User's
configured email address as part of the login process. When
attempting initial login, the User will be prompted to supply the

6-digit code, sent via the email address. If enabled, this type
can be configured to either always make the User subject to
Email Security Code authentication, or to make the User subject
to Email Security Code authentication only if the User's IP
address cannot be authorized.
Authorized IP addresses (either authentication method) —
This restricts the IP address(es) that the User can log in from to
one or more IP address values, subnets, or IP address ranges in
IPV4 address format. The configured list serves as a approved
range of valid IP address values.
Note: For more information about the Login screen and overall
process, please see About the eDiscovery Login Process.

About System User Roles
For full information about System User roles, see View and Manage
System Role-Based Permissions.
When you launch the New System User dialog, you will see a
System-level role preselected for you. This is the default Systemlevel role selected for new System Users. System Users with the
appropriate permissions can set an available role as the default role
using the Set as Default option, available from System Settings
> Provisioning > System Role Permissions. You can either use
the default role for the new System User, or you can select another
available role for the new System User.
Note the following restrictions for System User roles:
When creating a System User (or System Group), only System
Users with the IT Administrator or System Administrator role
can view and select the IT Administrator or System
Administrator role and these roles will not be available in the
Role drop-down menu for System Managers and System
Members. Similarly, when editing an existing System User (or
System Group) that has the IT Administrator or System
Administrator role, a System Manager or System Member can
see the System User's role but not change it; when editing a
System User in the System Manager or System Member role,
they will see only these roles in the drop-down.
Since there must be at least one System User in each of the
IT Administrator and System Administrator roles, the last
IT Administrator or System Administrator-level account cannot
be deleted, nor can the role for that last IT Administrator or
System Administrator-level account be modified.

Create or Edit a System User Entry on a
TransPerfect Authentication System
The following fields apply when Digital Reef is configured to use TP
Auth:
Note: System User attributes are editable after creation.
Email (required) – For a User with an existing TP Auth account,
enter the email address the User logs in with. This must be a
full email address, including the full domain with suffix. For a
User who does not yet have a TP Auth account, enter an
address eligible for TP Auth; this will be the User's login for all
uses of TP Auth going forward, including those outside of Digital
Reef.
Note: Generally, under TP Auth, email addresses and last
name/first name combinations must be unique across Digital
Reef; you cannot give a new User an email address or name
that matches an existing User's information. There is one
exception, however, as described in Add or Edit an Organization
User.
Role — A role represents a set of permissions to apply actions
to objects. As long as you have the appropriate permissions,
you can assign a System User to any role from the drop-down
list of those available, which includes the predefined roles and
any custom roles created. Predefined roles include the
following:
IT Administrator — Has full permissions to manage all
aspects of the system. Only a System User in the IT
Administrator role has the Add/Edit and Delete permissions
for Storage, which are needed to configure and manage the
system storage on which extracted documents and other

data are stored. (All System Roles have the View permission
for Storage.) This role cannot be deleted.
System Administrator — Has full permissions to manage
all aspects of the system except Add/Edit and Delete for
Storage. Only a System User in the IT Administrator or
System Administrator role can assign other System Users to
the System Administrator role. This role cannot be edited or
deleted.
System Manager (default) — Has permissions to manage
many aspects of the system, but not all. For example, a
System User in this role does not have permissions to
perform some IT-level functions.
System Member — This role has a smaller set of
permissions, mainly for viewing System-level information.
Password — If the email address you entered represents an
existing TP Auth account, this prompt is disabled. When adding
a User who does not yet have a TP Auth account, you must
specify the password for the new User; this will be the user's
password for all uses of TP Auth going forward, including those
outside of Digital Reef. When the System User is added, a
message containing the password is sent to the specified email
address.
First Name (required) – The first name of the User.
Last Name (required) – The last name of the User.
Description Closed Provides a helpful description of an
item. A description can have up to 255 characters. – An
optional description of this User.
The following options are available in the Authentication Options
section:
Password (always enabled) — This generally indicates that a
System User must always supply valid credentials to log in.

Authorized IP addresses (cleared by default but
configurable) — You can select this option when creating or
editing a System User entry. To restrict the IP address that the
User can log in from, use the box to supply one or more IP
address values, subnets, or IP address ranges in IPV4 address
format. What you specify produces a whitelisted range of valid
IP address values. Examples of valid IPV4 entries include
192.168.0.1 (single address), 192.168.0.1/16 (subnet), or
192.168.0.1-192.168.0.101 (range). Your IP address information
is validated when you click OK. If any IP address is in an invalid
format, you will see an error, Invalid IP Addresses and an
error in the table entry. Correct the invalid information
highlighted in the table entry (in a pink color) and try again. If
you want to delete an IP address entry, use the delete icon at
the right portion of the table.

Create or Edit a System User Entry on a
Standard Authentication System
The following fields apply when Digital Reef is configured to use
Standard Authentication:
Note: All fields apply during creation. Most System User attributes
can be edited after creation, except for Username and Password,
and role changes are permitted based on role-based permissions
(see About System User Roles).
Username * (required for a new entry only, cannot be edited)
– The Standard Authentication account name that this System
User will use to log in to the system. The value shown here
must be unique across the system and is validated. You cannot
edit the name of any configured User. A locally authenticated
username can include alphanumeric characters, spaces between
characters in the name (leading and trailing spaces are
ignored), and some supported characters (such as a period,
hyphen, underscore, and apostrophe). During validation, the
software will also allow characters from foreign languages (for
example, Korean characters). However, the following characters
are not supported and will generate an error message indicating
that your entry contains invalid characters:
!"#$%&*+/:;,<=>?@[\]^{|}~“”
Note: When logging in, locally authenticated users must specify
their username, followed by the @ symbol and then the Organization
name (as provisioned by the System Administrator). Usernames and
the Organization name are not case-sensitive. If the Organization is
myco and the user name is defined as LWeber, that User must use
the format <username>@org_name>, but the case is irrelevant
(that is, both LWeber@myco and lweber@myco are valid at login).

Email * (required) – The email address that enables the
System User to receive email from the software. This email
must be unique across the system. Remember to specify a full
email address (for example, remember to include .com). The
email address you supply will be validated when you click OK. If
the email address specified is not unique across the system, you
will see an error. If the email address specified is not in a valid
format, you will see the error message Email format error/s,
and you must address the error to submit the entry.
Role — A role represents a set of permissions to apply actions
to objects. As long as you have the appropriate permissions,
you can assign a System User to any role from the drop-down
list of those available, which includes the predefined roles and
any custom roles created. Predefined roles include the
following:
IT Administrator — Has full permissions to manage all
aspects of the system. Only a System User in the IT
Administrator role has the Add/Edit and Delete permissions
for Storage, which are needed to configure and manage the
system storage on which extracted documents and other
data are stored. (All System Roles have the View permission
for Storage.) This role cannot be deleted.
System Administrator — Has full permissions to manage
all aspects of the system except Add/Edit and Delete for
Storage. Only a System User in the IT Administrator or
System Administrator role can assign other System Users to
the System Administrator role. This role cannot be edited or
deleted.
System Manager (default) — Has permissions to manage
many aspects of the system, but not all. For example, a
System User in this role does not have permissions to
perform some IT-level functions.
System Member — This role has a smaller set of
permissions, mainly for viewing System-level information.

Password * (required for Standard Authentication only for new
Users only) — For a new System User entry, specify the
password for the new User. The password must meet the
password policy set by a System Administrator or you will see
an error when you click OK. The current password policy details
are displayed for you. You can click the icon to show the
password in clear text; once the password is shown, you can
click to hide the password again. When the new System User
has been added,
Change Password (applies to Standard Authentication only) —
Enables you to change the password for an existing System
User. The password policy details are displayed for you.
First Name (required) – The first name of the System User.
There are no naming restrictions for this option or the last
name.
Last Name (required) – The last name of the System User.
Description Closed Provides a helpful description of an
item. A description can have up to 255 characters. – An
optional description of this User.
Under the Authentication Options section, a Standard
Authentication User entry can support one or more of the following:
Password (always enabled) — This setting indicates that a
System User must always supply valid credentials to log in.
Email Security Code (cleared by default for new Users) —
As long as a Mail Server has been configured and is available on
the system, you can select this option if you want to enable
email-based Multi-Factor Authentication (MFA) for a System
User. You can select this option when creating or editing a
System User entry. If a Mail Server is not available on the
system, this option will not be available, and a tooltip informs
you that an Email Server has not been configured for this
system. Enabling this option requires a valid email address to
enable delivery of a 6-digit code to the User as part of the login
process. When attempting initial login, the User will be

prompted to supply the 6-digit code, sent via the email address.
(The code will expire after 10 minutes.) On the Enter Security
Code screen, the User supplies the code and has the option to
remember the device used for login; if set, a cookie will enable
future logins for the remembered device without requiring a
code. Once the User continues the login process with a valid
Code (and satisfies any additional conditions), the User will be
logged in and redirected to the Home page. If you select Email
Security Code, you can select one of the following options:
Always (the default when Email Security Code is
enabled) — Makes the User always subject to Email
Security Code authentication. If you only use this option
and do not enable Authorized IP addresses, the User is
emailed a Code at every login from a new device/browser.
If you use this option and also enable Authorized IP
addresses, the User is emailed a Code at every login from
a new device/browser, as long as the IP address used is in
the whitelisted range.
Only if user's IP address is not authorized — Makes
the User subject to Email Security Code authentication only
if the User's IP address cannot be authorized. A User's IP
address can be authorized when the Authorized IP
addressesoption is enabled and has at least one valid IP
address specified. When this option is selected, the
Authorized IP addresses option will be required.
Authorized IP addresses (cleared by default for new
Users; required when Email Security Code is set with the
Only if user's IP address is not authorized option) — You
can select this option when creating or editing a System User
entry. To restrict the IP address that the User can log in from,
use the box to supply one or more IP address values, subnets,
or IP address ranges in IPV4 address format. What you specify
produces a whitelisted range of valid IP address values.
Examples of valid IPV4 entries include 192.168.0.1 (single
address), 192.168.0.1/16 (subnet), or 192.168.0.1192.168.0.101 (range). Your IP address information is validated

when you click OK. If any IP address is in an invalid format, you
will see an error, Invalid IP Addresses and an error in the
table entry. Correct the invalid information highlighted in the
table entry (in a pink color) and try again. If you want to delete
an IP address entry, use the delete icon at the right portion of
the table.

OK or Cancel Actions
The following actions control whether the System User configuration
is saved or discarded:
OK – Verifies the new or modified System User configuration.
As long as you have addressed all required fields and there are
no errors, this option saves the new or modified System User
information. If you have not supplied all of the required
information, this button is unavailable (for example, if you
selected Authorized IP addresses, but you did not specify any IP
address values). It will also be grayed out if you have not made
any changes to an existing System User.
Cancel – Cancels the addition or modification of a System User
entry.
