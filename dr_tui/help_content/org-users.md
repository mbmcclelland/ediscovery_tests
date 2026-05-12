# Add or Edit an Organization User

*Source: Add or Edit an Organization Use - Unknown.pdf*

Add or Edit an Organization User
Home > selected Organization > menu or right-click >
Settings > General > Users > New User | Edit
Project > Settings drop-down > Organization Settings >
General > Users > New User | Edit
Home > selected Organization > menu or right-click >
Settings > General > Users > Retry TP Auth Setup

Requires Organization - Users - Add/Edit Permissions
Use this dialog to add a new Organization User to an Organization or
edit the information for an existing member. Organization Users and
Groups are created and exist only within a specific Organization and
cannot be added to others, whereas System Users and Groups can
belong to multiple Organizations and be added and removed as
needed by a System User with the required permissions.

Supported Authentication Methods
All User entries on a system are created based on the primary
authentication method configured for the system, as follows:
TransPerfect Authentication (default) — Also known as
TP Auth, this method requires setup and management of a
corporate-assigned email address and password for an
Organization User. A User entry created in eDiscovery using TP
Auth requires an email address for the User to receive emails
from the software, but the User entry itself does not include a
username, nor does it enable specification of a password if the
User is already defined in TP Auth. (For TP Auth, the corporateassigned email address is effectively serving as a username.) TP
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

Create or Edit an Organization User Entry
on a TransPerfect Authentication System
The following fields apply when Digital Reef is configured for TP
Auth.
Note: Organization User attributes are editable after creation. Also
note that when you launch the New User dialog, a role is
preselected the default role for the Organization is preselected.
Users with the appropriate permissions can set an available role as
the default role using the Set as Default option, available from
Organization Settings > General > Role Permissions. You can
either use the default role for the new User, or you can select
another available role for the new User.
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
exception, however. To allow the same individual to have access
to multiple Organizations through one set of TP Auth
credentials, create an Organization User in each of the desired
Organizations, using the same email address, first name, and
last name for both (adding the Users to Projects as needed).
When the individual using the email address logs in, they belong
to all such Organizations.

Role — The User's Organization role within the project. Like a
System role, an Organization role represents a set of
permissions to apply actions to objects. If you have the
appropriate permissions you can select the default role
(determined by the Set as Default option on the Role
Permissions page), another of the predefined roles, or a
custom role created for the Organization. By default, the
predefined Organization roles have the following permissions:
Organization Administrator — Always has permissions
to manage all Organization Settings and all aspects of
Projects within the Organization; cannot be edited or
deleted.
Project Administrator — Has view permissions for all
Project Data nodes in the Navigation Tree and add/edit
permissions for some of those nodes, such as Tags, Folders,
Saved Searches, Workflows, Comparisons, and Synthetic
Documents. Also has document-related permissions to add
or remove Tags from documents and documents from a
Folder, download native document and PDFs, and view
document reports, as well as view permissions for some
settings and the ability to edit the list of Metadata View
Fields.
Project Member – Has limited permissions to perform
general document search and analysis, but not to control
any aspects of the Project.
Claimant — Used in Reef Claims (previously known as
Class Action) Projects on a Reef Express system; not
intended for use in eDiscovery.
Password — If the email address you entered represents an
existing TP Auth account, this prompt is disabled. When adding
a User who does not yet have a TP Auth account, you must
specify the password for the new User; this will be the user's
password for all uses of TP Auth going forward, including those
outside of Digital Reef. When the Organization User is added, a

message containing the password is sent to the specified email
address.
First Name (required) – The first name of the User.
Last Name (required) – The last name of the User.
Description Closed Provides a helpful description of an
item. A description can have up to 255 characters. – An
optional description of this User.
The following options are available in the Authentication Options
section (with the needed permissions):
Password (always enabled) — This generally indicates that an
Organization User must always supply valid credentials to log in.
Authorized IP addresses (cleared by default but
configurable) — You can select this option when creating or
editing an Organization User entry. To restrict the IP address
that the User can log in from, use the box to supply one or
more IP address values, subnets, or IP address ranges in IPV4
address format. What you specify produces a whitelisted range
of valid IP address values. Examples of valid IPV4 entries
include 192.168.0.1 (single address), 192.168.0.1/16 (subnet),
or 192.168.0.1-192.168.0.101 (range). Your IP address
information is validated when you click OK. If any IP address is
in an invalid format, you will see an error, Invalid IP
Addresses and an error in the table entry. Correct the invalid
information highlighted in the table entry (in a pink color) and
try again. If you want to delete an IP address entry, use the
delete icon at the right portion of the table.

Create or Edit an Organization User Entry
on a Standard Authentication System
The following fields apply when Standard Authentication is
enabled on a system (a red asterisk * in the UI indicates a required
field):
Note: All fields apply during creation. Most User attributes can be
edited after creation, except for Username and Password. Also note
that when you launch the New User dialog, the default role for the
Organization is selected; you can select another available role if
desired. Users with the appropriate permissions can set an available
role as the default role using the Set as Default option, available
from Organization Settings > General > Role Permissions.
Username * (required for a new entry only, cannot be edited)
– The Standard Authentication account name that this User will
use to log in to the system. The value shown here must be
unique across the Organization and the system and is validated.
You cannot edit the name of any configured User. A locally
authenticated username can include alphanumeric characters,
spaces between characters in the name (leading and trailing
spaces are ignored), and some supported characters (such as a
period, hyphen, underscore, and apostrophe). During validation,
the software will also allow characters from foreign languages
(for example, Korean characters). However, the following
characters are not supported and will generate an error
message indicating that your entry contains invalid characters:
!"#$%&*+/:;,<=>?@[\]^{|}~“”
Note: When logging in, locally authenticated users must specify
their username, followed by the @ symbol and then the Organization
name (as provisioned by the System Administrator). Usernames and
the Organization name are not case-sensitive. If the Organization is

myco and the user name is defined as LWeber, that User must use
the format <username>@org_name>, but the case is irrelevant
(that is, both LWeber@myco and lweber@myco are valid at login).
Email * (required) – The email address that enables the User
to receive email from the software. This must be a full email
address, including the full domain with suffix.
Role — The User's Organization role within the project. Like a
System role, an Organization role represents a set of
permissions to apply actions to objects. If you have the
appropriate permissions you can select the default role
(determined by the Set as Default option on the Role
Permissions page), another of the predefined roles, or a
custom role created for the Organization. By default, the
predefined Organization roles have the following permissions:
Organization Administrator — Always has permissions
to manage all Organization Settings and all aspects of
Projects within the Organization; cannot be edited or
deleted.
Project Administrator — Has view permissions for all
Project Data nodes in the Navigation Tree and add/edit
permissions for some of those nodes, such as Tags, Folders,
Saved Searches, Workflows, Comparisons, and Synthetic
Documents. Also has document-related permissions to add
or remove Tags from documents and documents from a
Folder, download native document and PDFs, and view
document reports, as well as view permissions for some
settings and the ability to edit the list of Metadata View
Fields.
Project Member – Has limited permissions to perform
general document search and analysis, but not to control
any aspects of the Project.
Claimant — Used in Reef Claims (previously known as
Class Action) Projects on a Reef Express system; not
intended for use in eDiscovery.

Password * (required for new Organization Users only) — For
a new Organization User entry, specify the password for the
new Organization User. The new password must meet the
password policy set by a System Administrator or you will see
an error when you click OK. The current password policy details
are displayed for you. You can click the icon to show the
password in clear text; once the password is shown, you can
click to hide the password again.
Change Password — Enables you to change the password for
an existing Organization or System User. The current password
policy details are displayed for you.
First Name (required) – The first name of the User. There are
no naming restrictions for this option or the last name.
Last Name (required) – The last name of the User.
Description Closed Provides a helpful description of an
item. A description can have up to 255 characters. – An
optional description of this User.
Under the Authentication Options section, a Standard
Authentication User entry can support one or more of the following:
Password (always enabled) — This setting indicates that an
Organization User must always supply valid credentials to log in.
Email Security Code (cleared by default for new
Organization Users) — As long as a Mail Server has been
configured and is available on the system, you can select this
option if you want to enable email-based Multi-Factor
Authentication (MFA) for an Organization User. You can select
this option when creating or editing an Organization User entry.
If a Mail Server is not available on the system, this option will
not be available, and a tooltip informs you that an Email Server
has not been configured for this system. Enabling this option
requires a valid email address to enable delivery of a 6-digit
code to the User as part of the login process. When attempting
initial login, the User will be prompted to supply the 6-digit
code, sent via the email address. (The code will expire after 10

minutes.) On the Enter Security Code screen, the User supplies
the code and has the option to remember the device used for
login; if set, a cookie will enable future logins for the
remembered device without requiring a code. Once the User
continues the login process with a valid Code (and satisfies any
additional conditions), the User will be logged in and redirected
to the Home page. If you select Email Security Code, you can
select one of the following options:
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
can select this option when creating or editing an Organization
User entry. To restrict the IP address that the User can log in
from, use the box to supply one or more IP address values,
subnets, or IP address ranges in IPV4 address format. What you
specify produces a whitelisted range of valid IP address values.
Examples of valid IPV4 entries include 192.168.0.1 (single
address), 192.168.0.1/16 (subnet), or 192.168.0.1192.168.0.101 (range). Your IP address information is validated
when you click OK. If any IP address is in an invalid format, you

will see an error, Invalid IP Addresses and an error in the
table entry. Correct the invalid information highlighted in the
table entry (in a pink color) and try again. If you want to delete
an IP address entry, use the delete icon at the right portion of
the table.
