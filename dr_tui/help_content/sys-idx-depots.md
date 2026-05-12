# Add Storage or Edit Document Storage

*Source: Add Storage or Edit Document St - Unknown.pdf*

Add Storage or Edit Document Storage
Not in Use
Home > Settings drop-down > System Settings >
Provisioning > Storage > New Storage...
Project > Settings drop-down > System Settings >
Provisioning > Storage > New Storage...
Home > Settings drop-down > System Settings >
Provisioning > Storage > View/Edit...
Project > Settings drop-down > System Settings >
Provisioning > Storage > View/Edit...
A System User in the IT Administrator role can use the New Storage
dialog to configure system storage as either a new document
storage location or the index storage location (if it is not yet
configured), and the View / Edit Storage dialog to view and validate
existing storage locations as well as reconfigure a document storage
location that currently has no data on it. By default, System Users in
other roles can view and validate storage only. For information about
System-level permissions, see View and Manage System Role-Based
Permissions.

Add Storage
To add a storage location, supply the following information:
Name Closed The unique name of an item. For many
items, the name can have up to 100 characters. Some
items, such as a Connector name, can have up to 255
characters. An Excluded Content Block name is limited
to 32 characters. – A descriptive name of up to 100
characters that must be unique across the system. The name
can include alphanumeric and some other supported characters
(such as a hyphen, period, or underscore), as well as some
foreign languages characters. However, spaces and the
following characters are not supported:
!"'#$%&*+/:;<=>?@[\]^{|}~“”
Storage Type — Document (multiple locations possible) or
Index (one location only).
IP Address / Host Name — Identify the storage host.
Storage Path — Select your intended storage path from the
dropdown, which lists the paths available on the host you
specified.
File System / Protocol — Specifies whether the storage is
NFS or PanFS®.
After entering the needed information, you must click the Validate
button to validate that the storage you've configured exists and is
usable. If it is, you can click OK to add the storage location; if not,
correct the entries as needed and validate again.

Validate Storage or Edit Storage Not In Use
Click Validate to validate that the storage configured for the current
location exists and is usable.

If validation fails, or for another reason, you can update the
configuration as long as there is no data stored on the location (if
there us, the configuration fields are unavailable) and then validate
the new configuration. If validation succeeds, you can click OK to
save your changes. You cannot continue until the updated
configuration is validated.
