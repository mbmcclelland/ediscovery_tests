# Add or Edit a Project Data Area

*Source: Add or Edit a Project Data Area - Unknown.pdf*

Add or Edit a Project Data Area
Home > selected Organization > menu or right-click >
Settings > Project Data Areas > New Data Area
Project > Settings drop-down > Organization Settings >
Project Data Areas > New Data Area

Requires Organization - Project Data Areas - Add/Edit
Permissions
Users in a role with the appropriate permissions can add a new
Project Data Area, a type of Data Area that uses a read/write NFS
Connector to support Project Export and Project Import operations
(that is, export of a Project and subsequent import of a Project). The
Project Export and Import process, referred to as Project Portability,
allows a Project to be saved and later restored and then used within
the context of a new Project. Only read/write NFS Connectors can be
used to create Project Data Areas.
Note: Project Portability requires the definition and use of a
read/write NFS Connector and associated Project Data Area (Project
location) on both the Project Export side and the Project Import side
(where the Import side references the exported Project's location). If
the Project Export/Import scenario involves the same Organization,
the same NFS Connector and Project Data Area can be used for the
Project Export and the Project Import. For more information on how
to export a Project, see Export a Project and How to Export a
Project. For more information on how to import a Project, see
Import a Previously Exported Project into a New Project and How to
Import a Project.
After you add a Project Data Area, you can edit the Data Area by
selecting the Project Data Area in the list, editing the fields that
support edits, and then applying the changes. You can validate the
Project Data Area at any time.

New Project Data Area Options
Supply the following information for a new Project Data Area:
Name Closed The unique name of an item. For many
items, the name can have up to 100 characters. Some
items, such as a Connector name, can have up to 255
characters. An Excluded Content Block name is limited
to 32 characters. (required) — Assign a name that will be
used to represent the Project Data Area. The case-sensitive
name must be unique across all Data Areas within the
Organization, and you will see an error when you try to create
the area if the name itself is not unique. As long as the name
and path (Folder) are unique as a pair, the Data Area will be
created using the specified name (if valid). If both the name
and path (Folder) selection are not unique as a pair, then the
Data Area will be generated using the specified name with an
appended _ and value (for example, myprojda_1). The Project
Data Area name can include alphanumeric characters, and some
supported characters (such as a hyphen, period, or underscore).
During validation, the software will also allow characters from
foreign languages (for example, Korean characters). However,
spaces are not supported for names, and the following
characters will generate an error message indicating that your
entry contains invalid characters:
!"'#$%&*+/:;<=>?@[\]^{|}~“”
Description Closed Provides a helpful description of an
item. A description can have up to 255 characters. —
Assign a helpful description of this Project Data Area.
Connector (required) — Select a Connector from the list of
available read/write NFS Connectors. When you select a
Connector, the appropriate Folder hierarchy appears to the right.
Each Connector has the following information:

Connector Name – A descriptive name that appears in
lists to identify the Connector. This can be an alphanumeric
name of up to 32 characters to the Connector. The name
can have an underscore (_), as well as spaces. The name
must be unique within the Organization. The name is
validated.
Description – A helpful description of the Connector.
Type – Displays the type of Connector (in this case, NFS).
Mode – Displays the mode of the Connector, either
Read/Write or Read Only. The Connector mode cannot be
edited.
Server — Displays the IP address or Fully Qualified Domain
Name of the mount point.
Path — Displays the Connector path (mount information).
Folder — After you select a Connector, you can use this box to
view the list of available Folders and make a selection, which
populates the Path field.
Path — Selecting a Folder location for the Project Data Area
populates the Path field. If you do not select a Folder location,
the Project Data Area is created at the Connector root. If you
want, you can edit this path. If you specify a Folder that has not
been created yet, the validation will fail, but you will still be able
to create the Data Area.
Create Data Area — Commits the configuration of the Project
Data Area.
Cancel — Cancels the creation of the Project Data Area.

Edit Project Data Area Options
After you create a Project Data Area, you can edit some information
for the Project Data Area:
Name (editing allowed)
Description (editing allowed)
Connector (no editing allowed) — You cannot change the
Connector for the Project Data Area.
Path (editing allowed) — You can change the selected Path for
the Project Data Area by selecting another Folder for the
Connector.
Save — Commits the configuration changes to the Project Data
Area.
Cancel — Cancels and changes to the Project Data Area.
