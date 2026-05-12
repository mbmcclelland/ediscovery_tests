# Monitor Status for Items Used by Your

*Source: Monitor Status for Items Used b - Unknown.pdf*

Monitor Status for Items Used by Your
Project
(System Status: Critical) or (System Status: Warning)
on main Project toolbar instead of

Requires Project Monitoring Access Permissions

Main Toolbar Status
A System Status icon appears on the top toolbar instead of the book
icon if a component used by your Project is in a Critical or
Warning state. If you click the icon, you can determine the status for
the following:
Data Locations – The Import and Export Data Areas
associated with the Connectors used in your Project.
Processing Components – The Analytic Node resources
supporting your Project.
Storage Depot – NFS storage supporting your Project.
The information is auto-updated on a routine basis.
Note: With the appropriate permissions, you will see the Warning
icon if one or more of the components is in a Warning state. You will
see the Critical icon if any of the three major components (Data
Locations, Processing Components, or Storage Depot) are in the
Critical state. The Critical icon indicates that one or more items
under Project Monitoring require immediate attention (such as a
Storage Depot failure). If you see this icon, contact your System
Administrator right away. The Warning icon alerts you that a system
item used by your Project warrants attention, even though it is not
preventing the system from functioning overall. You should notify
your System Administrator so that the issue can be investigated.

System Status
This popup displays the status for three categories of items
(components) that affect the functioning of your Project.
Component – The category for the item (Data Locations,
Processing Components, or Storage Depot).
Status – The appropriate overall status for an item affecting
this Project in the Organization.

Data Locations
You can interpret the overall monitoring status for Data Locations as
follows:
Available – All Data Locations (Import or Export Data Areas)
are online and available.
Warning – One or more Data Locations (Import or Export
Data Areas) are not operating optimally (for example, a single
Data Area of a Connector may be having issues).
Critical – All Data Locations (all Import or Export Data Areas
associated with Connectors used by your Project) are in a failure
state and unavailable (not in service).

Processing Components
The Processing Component status is a rolled-up status for all
Analytic Node Component resources (the Parsing Manager, Collection
Manager, Index Manager, and Export Manager for each Analytic
Node providing resources to your Project). You can interpret the
overall monitoring status for Processing Components as follows:
Available – All Processing Components (that is, all
components used by the Analytic Nodes providing resources to
your Project) are online and available.

Warning – One or more Processing Components are not
operating optimally (for example, a single Component such as
an Index Manager may be having issues).
Critical – All Processing Components (that is, all components
used by the Analytic Nodes providing resources to your Project
are in a failure state and unavailable (not in service).

Storage Depot
The Storage Depot status, which provides temporary and permanent
NFS Document Storage, is either Available or Critical, as follows:
Available – The Storage Depot providing NFS storage for
your Project is online and available.
Warning – The Storage Depot providing NFS storage is not
operating optimally.
Critical – The Storage Depot providing NFS storage for your
Project is in a failure state and unavailable (not in service).
When you are done viewing the System Status information, click
Close.
