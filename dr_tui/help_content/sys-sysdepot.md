# Select a System Storage Depot

*Source: Select a System Storage Depot - Unknown.pdf*

Select a System Storage Depot
Home > Settings drop-down > System Settings >
Configuration > System Storage Depot
Project > Settings drop-down > System Setting >
Configuration > System Storage Depot
The System Settings > System Storage Depot page allows
System Users in the IT Administrator role to configure the System
Storage Depot that will be used by Digital Reef for the lifetime of the
system. By default, users in other System roles can access this page
to review the depot's data storage. (For information about Systemlevel permissions, see View and Manage System Role-Based
Permissions.)
When no System Storage Depot yet exists, the System Storage
Depot page can be used to configure storage for the Depot from
provisioned read/write system storage; once this is done, this screen
instead displays the name and path of the Depot, which cannot be
changed, and provides no options to the user.
The System Storage Depot is required for the following:
To ensure that a Project's Audit Log is archived automatically
upon deletion of the Project. A Project cannot be approved for
deletion unless the Storage Depot has been configured. After it
is in place, a user with the appropriate permissions can use
System Settings > Delete Pending Projects to approve the
deletion of a Project, and then use System Settings >
Deleted Projects to download the Audit Log of a deleted
Project.
To store Virus Detection definitions (the files used to identify
specific viruses). No Virus Detection updates can occur unless
the Storage Depot has been selected. After it is in place,

automatic Virus Detection updates can occur on a daily basis at
2 am, or when an update is requested by a user.

Select Storage for the System Storage
Depot
System Storage must be provisioned before the Depot is configured.
Typically, the System Storage Depot is located on the main System
Storage.
To establish a System Storage Depot when one does not yet exist,
click the Select System Storage for Depot option and select from
the list of available storage locations. Ensure that the location you
select provides enough space for storing the Audit Log indices of
Projects that are deleted (500 GB to 1 TB is recommended). Virus
definitions typically require less than 1 GB.
The list contains only available read/write System Storage. When
you have selected a location, click the Validate button to validate
that the storage you've configured exists and is usable. If it is, you
can click OK to add the storage location; if not, correct the entries
as needed and validate again. When you click OK, the Depot is
established, Virus Detection updates are enabled, and Project Audit
Logs can be automatically archived upon deletion of a Project.
