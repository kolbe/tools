The idea behind these scripts is that an instructor can run them shortly before, during, and immediately after a class to create, manage, and clean up the resources they'll need without having to pay for them to be running for a long period before the class starts. After the class is finished, the instructor should delete the resources ASAP. Classes should include materials that give students the information they need to recreate the lab environment(s) on their own, if they want to re-do the lab to reinforce learning during the course.

The `create-instances.py` script can be used to create a large number of uniform EC2 instances to be used by students taking a class that involves deploying and using TiDB Cluster. It will create a subnet, a security group, and a given number of instances of a given type for each "seat" in the class; each "seat" also has its own unique key pair as well as system password used for all instances associated with the seat.. The instructor can either provide a "course ID" (a unique identifier for a single instance of a course delivery), or one will be generated. This ID is used to tag resources created by the course and is passed to the `delete_course.bash` script when it's time to destroy resources.

The `create-instances.py` script writes to standard output a JSON file that contains resource IDs and per-seat information about the unique ssh key pairs, passwords, instance IP addresses, etc., for each seat. The instructor is responsible for sharing that information with each student.

The `instances-per-student.py` script takes as input the JSON file output by `create-instances.py`. It will create a directory based on the course ID, and a file in that directory for each student; the file consists of the student's private SSH key and a json structure that lists all their instances.

After the resources are deployed, any IP will be able to connect to the EC2 instances using SSH, but will *not* be able to connect using other ports (such as 3000 for Grafana or 2379 for the TiDB Dashboard).

The `modify-security-group.py` script can be used to "open" the security group to allow connections from the students' Public IP addresses. The instructor should collect the list of IP addresses of students at the beginning of the class. The best mechanism for doing that remains to be defined, but it's worth a quick note here that you can always load [icanhazip.com] in a web browser or curl to find a machine's public IP address. The instructor can either pass the IP addresses to the script as command-line parameters or put them in a text file, one-per-line, and send that file to the standard input of the script.

 
The `delete_course.bash` script takes one or more course IDs as arguments and deletes all resources associated with those courses created by `create-instances.py`.


