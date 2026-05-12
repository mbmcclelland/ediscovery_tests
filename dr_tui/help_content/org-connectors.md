# Create or Edit a Connector

*Source: Create or Edit a Connector - Unknown.pdf*

Create or Edit a Connector
Home > selected Organization > Settings > Connectors >
New Connector
Project > Settings drop-down > Organization Settings >
Connectors > New Connector
Home > selected Organization > Settings > selected
Connector > Connectors > Edit
Project > Settings drop-down > Organization Settings >
Connectors > selected Connector > Edit

Requires Organization - Connectors - Add/Edit Permissions
Users with the appropriate permissions can create a Connector
Closed An entity that provides access to content repositories of a
specific type (for example, NFS, CIFS, MS SharePoint, or MS
Exchange. A Connector identifies a server and operates either readonly or read/write to accommodate data import or export. of a type
to provide access to a server or storage area. Each Connector you
define can then be associated with one or more data locations
(areas) to use for data import or export, depending upon the
intended use (and Read Only or Read/Write mode) of the Connector.
Note: An NFS Connector can be configured read/write to support
Project Export and subsequent Project Import (also called Project
Portability). Once you define an NFS Connector for this purpose, you
can then create one or more Project Data Areas (locations) for that
Connector.
For example, an NFS or CIFS Connector uses a server mount point,
and then one or more data areas can be configured to point to
existing subdirectories under the Connector mount point. Connectors
such as Microsoft SharePoint and Microsoft Exchange require
specification of a URL to the server.

You can currently configure one of these types of Connectors:
Note: Always see the Digital Reef Change Notes for the latest
information about Connector support.
NFS
CIFS
Microsoft Exchange
Microsoft SharePoint
The Digital Reef system currently supports the following types of
Connectors for both import and/or export operations (using
configured export data areas):
NFS Connector, which can be configured Read Only to support
data Import or Read/Write to additionally support selected
data Export, or dedicated Project Import/Export
CIFS Connector, which can be configured Read Only to support
data Import or Read/Write to additionally support data Export
The following Connectors currently support import operations only
(which means it is appropriate to use the Connector default mode of
Read Only):
Microsoft Exchange Connector
Microsoft SharePoint Connector

New Connector Options
Name Closed The unique name of an item. For many
items, the name can have up to 100 characters. Some
items, such as a Connector name, can have up to 255
characters. An Excluded Content Block name is limited
to 32 characters. (required) — Assign a descriptive,
alphanumeric name (up to 255 characters) to identify the
Connector. The name you select must be unique across the
system. If it is not, you will see an error. The name can include
alphanumeric characters, and some supported characters (such
as a hyphen, period, or underscore). During validation, the
software will also allow characters from foreign languages (for
example, Korean characters). However, spaces as well as the
following characters are not supported for Connector names and
will generate an error message indicating that your entry
contains invalid characters:
!"'#$%&*+/:;<=>?@[\]^{|}~“”
Description Closed Provides a helpful description of an
item. A description can have up to 255 characters. —
Optionally supply a helpful description of the Connector.
Type (required) — Click the box that represents the
appropriate Connector type: NFS (the default), CIFS, MS
Exchange, or MS SharePoint.
Connector Configuration:
Mode (required for NFS and CIFS, always Read Only for
MS Exchange and MS SharePoint) — For an NFS or CIFS
Connector, keep the default of Read Only if you want the
Connector to handle import operations only (for example, to
support the ability to add Data Sets). If this Connector is
intended to support export operations (for example, export of

select data or an entire Project), be sure to select Read/Write.
NFS and CIFS Connectors support Read/Write. A Connector set
to Read/Write supports export through an Export Data Area (for
the export of selected data in a Project) or Project Data Area
(for Export of an entire Project). The Microsoft Exchange
Connector and SharePoint Connector are always Read Only.
Note: For options taking an IP address, you have the option of
specifying a Fully Qualified Domain Name, as long as the name can
be resolved (for example, using DNS).
ClosedNFS-specific Connector Options
PanFS® — Select this checkbox if you want the NFS
Connector to support PanFS DirectFlow® mode instead of the
standard NFS mode. When you configure an NFS Connector to
use this mode, the Connectors Summary displays a type of NFS
(PanFS).
Note: Before you can successfully use PanFS, setup procedures are
required. Please consult your System Administrator, who should
perform the PanFS required setup procedures.
Server (required) — Specify the IP address or Fully Qualified
Domain Name (for example, nas11.dhcp.hq.billesken.com) of
the share (mount point). Once you specify the FQDN or IP
address, the information is validated, and you can view the
available mounts.
Filter Filter by share.... — You can use the Filter text box at the
top right to filter the list of shares. (The icon indicates that
filtering is available.) Using the Filter box enables you to
pinpoint the items you want to work with based on a quick Filter
term search containing one or more characters you enter. You
can explicitly apply a filter by typing one or more characters in
the text box and clicking Enter (the return key). If you type one

or more characters in the text box, the software will
automatically apply the filter for you, and the text box changes
to a yellow background color. For any applied filter, you can then
clear the filter by removing the text in the box and clicking
Enter, by removing the text from the box, or by clicking the
that appears at the far right of the Filter box. Clearing a filter
restores the list to its original state.
Path (required) — After you specify a valid IP Address or
hostname, you can use this box to view the list of available
shares (mounts) in a Folder view and make a selection. Once
you select a Folder, it is highlighted.
ClosedCIFS/SMB-specific Connector Options
When you select CIFS, the following options and required fields
apply:
Under Connector Configuration:
Protocol: (required) — Select either FQDN/IP (the default) or
NetBIOS.
Authentication type:
NONE — anonymous login. The user can attempt to log in
without a username and password.
NTLM (the default) — Windows challenge/response
authentication protocol used with SMB. NTLM is supported
by most NAS devices and by pre-Windows NT 4. (SP4)
systems. NTLM provides basic password encryption and
username and password authentication.
NTLMI — Adds password signing to NTLM.
NTLMV2 — NTLM Version 2 provides: Stronger password
encryption, support for both NT 4.0 (SP4) and NT Serverbased systems such as XP. This is the default behavior to
the required protocol for Vista and MS Server 2008.
NTLMV2I — Adds password signing to NTLMV2.

Note: In general, ntlmi and ntlm are the recommended
authentication types and should be considered before ntlmv2
and ntlmv2i.
If you select an authentication type other than NONE, you must
supply credentials and the workgroup/domain or you will not be
able to validate or create the Connector:
Username — Supply a valid login name for the CIFS/SMB
device.
Password — Supply a valid password for the CIFS/SMB
login name.
Workgroup or domain name: — Identify the workgroup
or domain on the CIFS/SMB device into which the system
will authenticate. When you are configuring a CIFS
Connector as read/write to perform CIFS-CIFS migration,
you must include the workgroup or domain in order to
replicate the permissions between source and destination.
Support Legacy Mode — This checkbox option
determines whether the CIFS Connector uses a more recent
Server Message Block (SMB) protocol version or an older,
legacy protocol version to establish the underlying
connection. By default, this checkbox is cleared, which
provides support for the more recent SMB protocol versions
(for example, SMB 2.1 and 3) that should be suitable for
most CIFS Connectors. If you enable this checkbox option,
the CIFS Connector uses the older SMB version 1 protocol
instead, which should only be necessary if you have trouble
validating your CIFS Connector and you know that the
other provided CIFS information is correct.
Provide Server and Share information:
Server (required) — Your choice of Protocol dictates how
you provide the Server information in the text box. If you
keep the default of FQDN/IP, specify either the IP address
or the fully qualified domain name (for example,
ae1.hq.billesken.com) of the mount point. After you type
the IP address, validation occurs, and you should see a list
of the available mounts. If you selected NetBIOS instead,

the box hint text changes to NetBIOS name to indicate that
you must identify the NetBIOS name of the device
exporting the storage. After you type the NetBIOS name,
validation occurs, and you should see a list of the available
mounts.
Filter Filter by share.... — You can use the Filter text box
at the top right to filter the list of shares (mounts). (The
icon indicates that filtering is available.) Using the Filter box
enables you to pinpoint the items you want to work with
based on a quick Filter term search containing one or more
characters you enter. You can explicitly apply a filter by
typing one or more characters in the text box and clicking
Enter (the return key). If you type one or more characters
in the text box, the software will automatically apply the
filter for you, and the text box changes to a yellow
background color. For any applied filter, you can then clear
the filter by removing the text in the box and clicking Enter,
by removing the text from the box, or by clicking the that
appears at the far right of the Filter box. Clearing a filter
restores the list to its original state.
Path (required)— After you specify a valid IP Address or
fully qualified domain name (for FQDN/IP), or a NetBIOS
name (for NetBIOS), you can use this box to view the list of
available shares (mounts) in a Folder view and make a
selection. Once you select a Folder, it is highlighted.
ClosedMicrosoft Exchange Connector Options
For any Exchange configuration, select MS Exchange as the
Connector type. This Connector type is always read only and
connects to a Microsoft Exchange server.
Note: Before you create a Microsoft Exchange Connector, make sure
that you have a complete Windows Active Directory Server
configuration, complete with DNS support.
Local Tab: Required Information for Local MS Exchange

To define a Local Microsoft Exchange configuration, you must select
the Local tab and supply the following required information:
Specify credentials for the named local Microsoft Exchange
server. The credentials must have permissions to perform
impersonation (that is, the user account provided must
be able to impersonate the users whose mailboxes are
going to be collected, and the account must have a user
mailbox):
Username (required) — Supply a valid login name for the
Exchange server (for example, Administrator). The user
account provided must be able to impersonate the users
whose mailboxes are subject to collection. Also, this
Exchange Server user account must have a user mailbox. If
this user account does not have a user mailbox, the
Connector will not work. (This is important to check
because an Administrator account may not have a user
mailbox by default.) For Office 365, this is just the name
portion of the Global Administrator account (for example,
for Administrator@<tenant>.com, you would supply
just Administrator).
Password (required) — Supply a valid password for the
Exchange username. For Office 365, this is the password
for the Global Administrator account. You can click the
icon to show the password in clear text; once the password
is shown, you can click to hide the password.
Domain name (required) — Supply the name of the
domain for the Exchange server (for example,
myeng.mydev8.com).
Server (required) — Supply the server URL for the
Microsoft Exchange Server (for example,
https://exchange01.myeng.mydev8.com).
Office 365 Tab: Required Information for Office 365 MS
Exchange

To have the Microsoft Exchange Connector support Office 365, you
must have registered your application with Office 365 using the
Microsoft portal and have your Tenant Domain, Application ID, and
Application Secret values. For Exchange, there is also an initial setup
procedure. The Office 365 registration process and additional setup
procedure for Exchange is described in a separate document,
available upon request from Digital Reef Customer Support. When
you have registered the application, have the required values, and
performed the initial setup procedure, you can configure the
Exchange Connector by selecting the Office 365 tab, which then
enables you to supply the following required information:
Tenant Domain (required) — Supply the Tenant Domain
information (Primary domain) that you specified when you
registered your application with Office 365. The Tenant Domain
uses the format <tenant>.onmicrosoft.com. Example:
someco@onmicrosoft.com
Application ID (required) — Supply the Application ID you
received when you registered your application with Office 365.
Application Secret (required) — Supply the Application
Secret (also known as the Client Secret) that was generated
when you registered your application with Office 365.
Refresh Token (optional ) — You can optionally supply a
Refresh Token value that ensures access until it expires (for
example, every 6 months). When the Refresh Token expires is
determined by the policies in place for the associated Azure
Active Directory account. The Refresh Token can be generated
as part of the Connector Setup procedure, described in a
separate document, available upon request from Digital Reef
Customer Support.
Note: If you have already configured a SharePoint Configuration for
Office 365, you can use the same Tenant Domain, Application ID,
and Application Secret values for the Exchange Connector. Once the
Connector has been established, you can click Edit to view and/or

change the Connector information. You will see the Refresh Token
field along with a Last Updated date that indicates when the
Refresh Token was last generated. The Last Updated date is in the
format YYYY-MM-DD HH:mm:ss.
ClosedMicrosoft SharePoint Connector Options
For any SharePoint configuration, select MS SharePoint as the
Connector type. This Connector type is always read only and
connects to a Microsoft SharePoint server.
Local Tab: Required Information for Local MS SharePoint
To define a Local Microsoft SharePoint configuration, you must select
the Local tab and supply the following required information:
Username (required) — Supply a valid login name for the
SharePoint server. Example: Administrator
Password (required) — Supply a valid password for the
SharePoint login name. You can click the icon to show the
password in clear text; once the password is shown, you can
click to hide the password.
Domain name (required) —Supply the Windows domain for
the specified user (for example, myeng1.mydev1.com).
Server (required) — Supply the root URL representing the
location of the target SharePoint server (for example,
http://sharepoint01.myeng1.mydev1.com). In the URL, specify a
Fully Qualified Domain Name (FQDN).
Office 365 Public/Private Sites Tab: Required Information
for Office 365 SharePoint Public/Private Sites
To have the Microsoft SharePoint Connector support Office 365, you
must have registered your application with Office 365 using the
Microsoft portal and have your Tenant Domain, Application ID, and
Application Secret values. The registration procedure is described in
a separate document, available upon request from Digital Reef
Customer Support. When you have performed the registration and

have the required information, you can configure the Connector by
selecting the Office 365 Public/Private Sites tab, which then
enables you to supply the following required information:
Tenant Domain (required) — Supply the Tenant Domain
(Primary domain) information that you specified when you
registered your application with Office 365. The Tenant Domain
uses the format <tenant>.onmicrosoft.com. Example:
someco@onmicrosoft.com
Application ID (required) —Supply the Application ID that
you generated when you registered your application with Office
365.
Application Secret (required) — Supply the Application
Secret (also known as the Client Secret) generated when you
registered your application with Office 365.
Refresh Token (optional ) — You can optionally supply a
Refresh Token value that ensures access until it expires (for
example, every 6 months). When the Refresh Token expires is
determined by the policies in place for the associated Azure
Active Directory account. The Refresh Token can be generated
as part of the Connector Setup procedure, described in a
separate document, available upon request from Digital Reef
Customer Support.
Note: The information you supply applies to both Public and Private
sites. Once the Connector has been established, you can click Edit
to view and/or change the Connector information, you will see the
Refresh Token field along with a Last Updated date that
indicates when the Refresh Token was last generated. The Last
Updated date is in the format YYYY-MM-DD HH:mm:ss.

After you fill out the required information for the Connector based on
its type, you can select from the following actions:

Validate — Validates the Connector information to ensure that
the Connector is accessible. If the Connector is valid, a
Validation successful message appears next to the Validate
button. Typically, it is a good idea to validate the information
before committing the configuration.
Create Connector — Commits the configuration of the
Connector.
Cancel — Cancels the operation.

Edit Connector Options
Once you create a given Connector, you can view the current
Connector information and edit some of the field information. You
can select a Connector and right-click to select the Edit option (or
use the ellipses at the far right). The following indicates which fields
are editable and which are not:
Name (no editing allowed)
Description (editing allowed)
Type (no editing of main Connector type allowed)
Mode (no editing allowed)
MS Exchange or MS SharePoint Type (no editing of Local or
Office 365 type allowed)
Local Fields for MS Exchange or MS SharePoint (editing
allowed)
Office 365 Fields for MS Exchange (editing allowed)
Office 365 Public/Private Sites for MS SharePoint (editing
also allowed for the Refresh Token)
PanFS®(NFS attribute; no editing allowed)
Server (editing allowed)
Path (editing allowed; see note)
Note: If you edit a Connector to change server information,
remember to select the appropriate path for that server. Note also
that you can update the editable fields for a deactivated Connector.
If you change the path for a Connector, when you save your
changes, you will see a warning message stating that changing the
path will require a system restart to propagate the change. You
should contact your System Administrator, who will decide when to
perform the restart.

Once you make any permitted changes to a Connector, you can then
Validate and click Save Changes. Click Cancel instead if you want
to discard your changes..
For a CIFS Connector, note that you can edit the checkbox setting
for Support Legacy Mode.
