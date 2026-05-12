# Add or Edit a System Group

*Source: Add or Edit a System Group - Unknown.pdf*

Add or Edit a System Group
Home > Settings drop-down> System Settings >
Provisioning > System Groups > New System Group |
Edit
Project > Settings drop-down > System Settings >
Provisioning > System Groups > New System Group |
Edit

Requires System Groups - Add/Edit permissions
If you have the appropriate System-level permissions, you can add a
new System Group entry or edit the information for an existing
System Group.
Note: You can use eDiscovery to select the member Organizations
for a System User or System Group as of 5.4.2.0.

New System Group or Edit System Group
Options
When you launch the New System Group dialog, you will see a
System-level role preselected for you. This is the default Systemlevel role selected for the System Group. System Users with the
appropriate permissions can set an available role as the default role
using the Set as Default option, available from System Settings
> Provisioning > System Role Permissions. You can either use
the default role for the new System Group, or you can select another
available role for the new System Group.
Note the following restrictions for System Group roles:
When creating a System Group, only System Users with the
System Administrator role can view and select the System
Administrator role for the Group. The System Administrator role
will not be visible in the role drop-down menu to System Users
who are not in the System Administrator role (for example,
those in the default System Manager role).
When editing an existing System Group that has the System
Administrator role, any System User who is not in the System
Administrator role (for example, those in the default System
Manager role) will only see the set System Administrator role
and will not be able to change it.
When editing an existing System Group that has a role other
than the System Administrator role, either the System User's
own Group or another Group, the System User will be able to
view and select available roles in the role drop-down menu
except the System Administrator role.
In general, note that there must be at least one System User in the
System Administrator role, the last System Administrator-level

account cannot be deleted, nor can the role for that last System
Administrator-level account be modified.
The following fields all apply when creating a System User; for
editing a System User, all except Username and Password generally
apply, with the previously noted limitations for role changes:
Name Closed The unique name of an item. For many
items, the name can have up to 100 characters. Some
items, such as a Connector name, can have up to 255
characters. An Excluded Content Block name is limited
to 32 characters.(required) – Specify the account name for
this System Group. The System Group must be unique across
other Groups. The System Group name must be unique and is
subject to validation upon creation. You cannot edit the name of
a configured System Group. The name can include alphanumeric
characters, spaces between characters in the name (leading and
trailing spaces are ignored), and some supported characters
(such as a period, hyphen, underscore, and apostrophe). During
validation, the software will also allow characters from foreign
languages (for example, Korean characters). However, the
following characters are not supported for Tag names and will
generate an error message indicating that your entry contains
invalid characters:
!"#$%&*+/:;,<=>?@[\]^{|}~“”
Description Closed Provides a helpful description of an item. A
description can have up to 255 characters. – An optional
description of the System Group.
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

OK or Cancel Actions
The following actions control whether the System Group
configuration is saved or discarded:
OK – Verifies the new or modified System Group configuration.
As long as you have addressed all required fields, this option
saves the new or modified System Group information.
Cancel – Cancels the addition or modification of the System
Group.
