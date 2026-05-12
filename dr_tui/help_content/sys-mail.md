# Configure an Email Server &

*Source: Add or Edit a System User - Unknown.pdf*

Configure an Email Server &
Notifications
System Setting > Configuration > Email Server &
Notifications

Requires System-level Email Server & Notifications - View
permissions to view the information, Add/Edit permissions
to supply or edit the information
System Users in a role with the appropriate System-level permissions
can use this screen to do the following:
Configure a mail server for the system, which permits
configuration of email notifications.
Establish email notifications for Users who should be notified of
Component Alerts (for example for component restarts) and
Virus Detection Update failures.
By default, System Users in the System Administrator or System
Manager role have permissions to manage the Email Server &
Notifications information. For information about System-level
permissions, see View and Manage System Role-Based Permissions.
Having a configured mail server also enables eDiscovery users to set
up and send email notifications for a selected Job or Work Basket
operation (when the job completes successfully or when it fails). See
Request a Job Notification for a Running Job and Request
Email Notification for a Task for more information.
You can have one mail server per system, or Digital Reef Realm. An
email server configuration can be edited, but not deleted.

Email Server Configuration
An email server configuration minimally requires identification of the
Simple Mail Transfer Protocol (SMTP) host and port through which it
is to communicate with Digital Reef. You can also specify the use of
SSL/TLS encryption and require SMTP authentication. The
configuration settings are as follows:
SMTP Host (required) — Specify the host of the Simple Mail
Transfer Protocol (SMTP) server by entering its host name or IP
address.
SMTP Host Port (required) — Specify the port that is
responsible for handling SMTP communication. The default port
is 25, which is the common default port for SMTP, but you can
specify a different port if your mail server's configuration
requires it.
Use SSL (optional) — Select the checkbox if you want to
protect communication with the SMTP server using
SSL/TLS encryption. When you select SSL, the SMTP Host Port
changes to 587, which is the common default port for secure
SMTP, but you can specify a different port if your mail server's
configuration requires it.
Use SMTP Authentication (optional) — Enable this option if
you want the SMTP client to authenticate based on the specified
User credentials (valid User ID and Password). By default, this
option is cleared, which means that no SMTP authentication is
performed; therefore, the User credentials do not apply and are
unavailable If you enable SMTP authentication, you must specify
the User Credentials (which are retained if you enable and then
disable SMTP authentication).
User ID (required when you select SMTP Authentication)—
If you have enabled SMTP Authentication, you must specify
the Administrator ID configured in the mail server that will
be used to send email.

Password (required when you select SMTP Authentication)
— If you have enabled SMTP Authentication, you must
specify the password of the Administrator configured in the
mail server. Once you type the password, you can click the
icon to show the password in clear text; once the
password is shown, you can click to hide the password
again.

Email Notifications
This section enables you to set up a list of email addresses that
should receive email notifications about either Component Alerts or
Virus Detection Update failures, as follows:

Component Alerts are sent to the listed email addresses when a
component (for example, the Service Tier on the Service Node,
an Analytic Node, or a Management Agent) is restarted.
Notification for a given component is sent once every 15
minutes. Therefore, if a component is restarted frequently, the
next notification for that component is sent only after 15
minutes of the previous notification.
A Virus Detection Update notification is sent only if an update
fails. In this case, an email is sent to the listed email addresses
with the subject Virus Detection Update Failed. The email
provides information (such as that an unexpected error occurred
while updating the Virus definition files).
When a notification is sent, the email subject will identify the
appropriate type of notification. A Component Alert Email will
identify Component Re-Started, and the email body will identify
the component.
Note: An email notification will be sent when any service goes into a
critical state (one email per critical event). For example, an email
notification will be sent if any services for an Analytic Node move to
a critical state.
Sample Component Re-Started Email Alert (Analytic Node):
Component:AE666_MA Restarted at:2015/07/28 13:49:39
Log into the appropriate Digital Reef application for more
information.

Send Email Notifications to:
Use the first text box to specify a valid email address (or pasted
email addresses) that can be used for notification and for sending a
test email. Once you have information in the first text box, another
will appear beneath it. You can add multiple entries for different
addresses, each in a separate text box entry.
A supplied email address is validated to ensure that it follows the
expected format. If the format is not valid, you will see an error.
To clear a text box entry with an email address, click the
appears in the far right of the text box.

that

To delete a given text box entry with an email address, click the
icon to the right of the line.
Once you have a valid mail server configuration that has been saved,
and one or more valid email addresses, you can send a test email to
either a single entry or to all supplied entries.
Send Test Email to All— Click this button to send a test email
to all supplied email addresses, assuming that the mail server
has been configured and that one or more of the email
addresses are valid. Otherwise, this button is unavailable.
Send Test Email — Click this button to send a test email to a
specific email address entry, assuming that the mail server has
been configured and the address is valid. Otherwise, this button
is unavailable.
A confirmation message will notify you when a test email has been
sent, and will identify the recipient email addresses.
Sample Test Email Text
Informational Notification:

Test Email
Additional Details:

Test Email
Log into the appropriate Digital Reef application for more
information.
