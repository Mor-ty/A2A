# Phase 2: Linux & Networking - Complete Interview Preparation Guide
## AI Support Engineer Role (5 Days - HIGH PRIORITY)

---

## ≡ƒôî OVERVIEW

Production troubleshooting is where support engineers shine. This phase covers the critical tools and knowledge needed to debug failing APIs, analyze system performance, and identify network issues. Expected to handle real-time incident response.

---

## SECTION 1: ESSENTIAL LINUX COMMANDS

### 1.1 Navigation & File Management

#### `ls` - List Files and Directories
**What it does:** Displays files and directories in a folder

```bash
# Basic listing
ls

# Detailed listing with permissions, owner, size
ls -l

# Show all files including hidden (starting with .)
ls -la

# Show file sizes in human-readable format
ls -lh

# Sort by modification time (newest first)
ls -ltr

# Show only directories
ls -ld
```

**Real-world production use case:**
```bash
# Check what log files exist in a service directory
ls -lh /var/log/myapp/
# Output: -rw-r--r-- 1 root root 125M May 23 10:30 application.log
# This tells you: readable file, 125MB size, last modified today
```

**Interview tip:** Mention that `-lh` is your go-to because it shows permissions (security checks), ownership (ownership issues?), size (is the log bloated?), and timestamp (recent activity?).

---

#### `cd` - Change Directory
**What it does:** Navigate to different directories

```bash
# Go to specific directory
cd /var/log

# Go to home directory
cd ~

# Go to previous directory
cd -

# Go up one directory
cd ..

# Go to root
cd /
```

**Real-world production use case:**
```bash
# A service crashed. Navigate to its logs
cd /var/log/service-name
# Now you're in position to examine logs
```

---

### 1.2 File Inspection & Search

#### `cat` - Display File Contents
**What it does:** Reads and displays entire file contents

```bash
# Display entire file
cat logs.txt

# Display multiple files
cat file1.txt file2.txt

# Add line numbers
cat -n logs.txt
```

**Production warning:** Avoid on large filesΓÇöwill flood your terminal!

```bash
# Γ¥î DON'T DO THIS on 500MB logs
cat /var/log/application.log

# Γ£à USE THIS INSTEAD
head -50 /var/log/application.log
```

---

#### `head` & `tail` - View File Start and End
**What it does:** Display beginning or end of files

```bash
# Show first 20 lines
head -n 20 logs.txt

# Show first 50 bytes
head -c 50 logs.txt

# Show last 10 lines
tail -n 10 logs.txt

# Show last 100 lines
tail -n 100 logs.txt

# Real-time monitoring (keep watching file as it grows)
tail -f logs.txt

# Real-time with line numbers
tail -fn 50 logs.txt

# Follow multiple files
tail -f /var/log/app1.log /var/log/app2.log

# Exit tail -f with Ctrl+C
```

**Real-world production use case - Critical for Support Engineers:**

Scenario: "The API is returning errors. What's happening?"

```bash
# Check the last 50 lines of the error log
tail -n 50 /var/log/api/error.log
# Output:
# 2025-05-23T10:45:23 [ERROR] Database connection timeout
# 2025-05-23T10:45:24 [ERROR] Retry attempt 1 of 3
# 2025-05-23T10:45:25 [ERROR] Retry attempt 2 of 3
# 2025-05-23T10:45:26 [ERROR] Database connection failed

# Watch logs in real-time while debugging
tail -f /var/log/api/app.log
# Now trigger the issue and watch errors appear in real-time
```

**This is CRITICAL:** Most production issues show the error trail in logs. Use `tail -f` to watch live errors as they happen.

---

#### `grep` - Search Text Patterns
**What it does:** Finds lines matching a pattern

```bash
# Search for specific text
grep "ERROR" logs.txt

# Count occurrences
grep -c "ERROR" logs.txt

# Show line numbers
grep -n "ERROR" logs.txt

# Case-insensitive search
grep -i "error" logs.txt

# Show 5 lines after match (context)
grep -A 5 "ERROR" logs.txt

# Show 5 lines before match
grep -B 5 "ERROR" logs.txt

# Show 5 lines before and after
grep -C 5 "ERROR" logs.txt

# Invert: show lines NOT containing pattern
grep -v "DEBUG" logs.txt

# Use regex patterns
grep "ERROR|WARN" logs.txt

# Search recursively in directory
grep -r "ERROR" /var/log/

# Count errors in multiple files
grep "ERROR" /var/log/*.log | wc -l
```

**Real-world production use case:**

Scenario: "We have thousands of log lines. Find all database errors with context"

```bash
# Find database errors and show surrounding context
grep -B 2 -A 10 "database error" /var/log/app.log

# Output:
# 2025-05-23T10:45:20 [INFO] Processing request
# 2025-05-23T10:45:21 [INFO] Connecting to database
# 2025-05-23T10:45:23 [ERROR] database error: connection pool exhausted
# 2025-05-23T10:45:23 [ERROR] Stack trace: java.sql.SQLException...
# 2025-05-23T10:45:23 [ERROR]   at com.app.db.ConnectionPool.getConnection
# ...
# 2025-05-23T10:45:24 [INFO] Retrying in 5 seconds

# Count how many database errors occurred
grep -c "database error" /var/log/app.log
# Output: 47

# Which types of errors are most common?
grep "ERROR" /var/log/app.log | grep -o "\[.*\]" | sort | uniq -c | sort -rn
# Output:
# 47 [DatabaseError]
# 12 [TimeoutError]
# 3  [ConnectionError]
```

**Interview tip:** Demonstrate you understand that grep is about finding patterns. Be ready to combine grep with other tools.

---

### 1.3 Text Processing

#### `grep` Combined with Other Tools

```bash
# Count specific error patterns
tail -f /var/log/app.log | grep "ERROR" | wc -l

# Extract specific field from logs
grep "ERROR" logs.txt | awk '{print $1, $2, $NF}'

# Find and remove lines with certain pattern
grep -v "DEBUG" logs.txt > cleaned.log

# Multiple grep filters (AND condition)
grep "ERROR" logs.txt | grep "database"

# Show errors from specific time range
grep "2025-05-23T10:4[5-9]" /var/log/app.log

# Find a pattern in all log files
grep -r "500 Internal" /var/log/ --include="*.log"
```

**Real-world production use case:**

API returns 500 errors. Find the root cause in logs:

```bash
# Find 500 errors with full context
grep -B 5 -A 5 "500 Internal Server Error" /var/log/api.log | head -50

# Count 500 errors by minute to see pattern
grep "500 Internal" /var/log/api.log | awk '{print $1}' | uniq -c

# See if it's a specific endpoint causing 500s
grep "500 Internal" /var/log/api.log | grep -o "/api/[^ ]*" | sort | uniq -c

# Output:
# 23 /api/users
# 5  /api/products
# 2  /api/orders

# Now you know /api/users is broken!
```

---

### 1.4 Process Management

#### `ps` - List Running Processes
**What it does:** Shows currently running processes

```bash
# List all processes
ps aux

# Explanation of ps aux output:
# USER    PID   %CPU %MEM   VSZ   RSS STAT START   TIME COMMAND
# root    1     0.0  0.1  225   60  S    May23   0:00 init
# app     1234  5.2  12.5 2850000 512000 S May23  1:30 java -jar app.jar

# Key fields:
# PID     = Process ID (needed for kill commands)
# %CPU    = CPU usage (is process eating CPU?)
# %MEM    = Memory usage (is process leaking memory?)
# VSZ     = Virtual memory size
# RSS     = Resident memory (actual RAM used)
# STAT    = Process state (S=sleeping, R=running, Z=zombie)
# COMMAND = The actual command

# Find specific process
ps aux | grep "java"

# Find process by name
ps aux | grep -i "mysql"

# Show process tree (parent-child relationships)
ps auxf

# Watch processes in real-time (like top but simpler)
watch -n 1 'ps aux | grep "java"'
```

**Real-world production use case:**

Scenario: "Application is using 50% CPU and consuming more memory over timeΓÇöis it a memory leak?"

```bash
# Check the problematic process
ps aux | grep "myapp"
# root    5432  50.2  18.5  4200000  750000  S  May23  5:30  java -jar myapp.jar

# That's 750MB of RAM. Is this normal or growing?
# Run this command every 5 minutes to monitor
watch -n 300 'ps aux | grep myapp'

# If RSS keeps growing: memory leak
# If CPU stays at 50%: CPU-bound process or infinite loop
# Solution steps:
# 1. Check logs for errors causing infinite loops
# 2. Check database queries for slow queries
# 3. Check if connections are being properly closed
```

---

#### `top` - Real-Time System Monitoring
**What it does:** Shows real-time CPU, memory, and process information

```bash
# Start top (press 'q' to quit)
top

# Non-interactive mode (useful for scripts)
top -b -n 1

# Monitor specific user's processes
top -u appuser

# Sort by memory usage
top -o %MEM

# Sort by CPU usage (default)
top -o %CPU

# Update every 5 seconds
top -d 5

# Get one snapshot for use in scripts
top -b -n 1 | head -20
```

**Real-world production use case:**

System is slow. Which process is the culprit?

```bash
# Show top CPU consumers
top -b -n 1 | head -20

# Output:
# PID  USER   %CPU %MEM  COMMAND
# 5234 root   45.2 12.5  /usr/bin/python3 train_model.py
# 4321 mysql  22.1  8.3   /usr/sbin/mysqld
# 3322 app    15.3  6.2   java -jar service.jar

# Now you know: Python training script is killing the CPU!
# Decision: Run it at night, or scale resources
```

---

#### `kill` - Terminate Processes
**What it does:** Sends signals to processes to stop them

```bash
# Graceful shutdown (SIGTERM)
kill 1234

# Force kill (SIGKILL)
kill -9 1234

# Kill all processes matching pattern
killall java

# Kill with specific signal (SIGTERM = 15)
kill -15 1234

# Kill process gracefully, then force if needed
kill 1234; sleep 5; kill -9 1234

# Kill entire process group (parent + children)
kill -TERM -1234  # negative PID = process group
```

**Real-world production use case:**

A hanging Java process won't stop. What to do?

```bash
# Step 1: Gentle shutdown
kill 5432

# Wait and check if it stopped
sleep 5 && ps aux | grep 5432

# If still running:
# Step 2: Force kill
kill -9 5432

# Verify it's gone
ps aux | grep 5432
# Should return nothing

# ΓÜá∩╕Å CAUTION: Use kill -9 only as last resort
# It doesn't give the process time to clean up (close DB connections, flush caches)
# Can cause data corruption if process had unsaved data
```

---

#### `chmod` - Change File Permissions
**What it does:** Controls who can read, write, execute files

```bash
# Permission format: chmod [user][operator][permission] file
# User: u (user), g (group), o (other), a (all)
# Operator: + (add), - (remove), = (set)
# Permission: r (read), w (write), x (execute)

# Make file executable
chmod +x script.sh

# Make readable by user only
chmod u=r file.txt

# Make readable/writable by user, readable by group
chmod u=rw,g=r file.txt

# Recursive: change directory and all contents
chmod -R 755 /var/www/html

# Numeric notation (commonly used):
# 4=read, 2=write, 1=execute
# User + Group + Other
chmod 755 file   # rwxr-xr-x (user: all, group/other: read+execute)
chmod 644 file   # rw-r--r-- (user: read+write, group/other: read)
chmod 600 file   # rw------- (user: read+write, others: nothing)
chmod 777 file   # rwxrwxrwx (everyone: all permissions)
```

**Real-world production use case:**

API service can't read its config file. Permission denied error.

```bash
# Check current permissions
ls -l /etc/myapp/config.yml
# -rw------- 1 root root  2048 May 23 10:00 config.yml

# Problem: File owned by root, readable only by root
# But the app runs as user 'appuser'

# Solution: Change permissions so appuser can read it
chmod 644 /etc/myapp/config.yml
# Now: -rw-r--r-- 1 root root

# Or better: change ownership to appuser
chown appuser:appuser /etc/myapp/config.yml

# Verify the service can now access it
sudo -u appuser cat /etc/myapp/config.yml
# Should work now
```

---

### 1.5 Network Tools

#### `curl` - Make HTTP Requests
**What it does:** Fetches HTTP content, tests APIs, debugs HTTP issues

```bash
# Basic GET request
curl https://api.example.com/users

# Include response headers
curl -i https://api.example.com/users
# Shows: HTTP/1.1 200 OK, then headers, then body

# Show only headers (useful for debugging)
curl -I https://api.example.com/users
# Just shows the headers

# Include request and response details
curl -v https://api.example.com/users
# Shows: request headers sent, response headers, body

# POST request with JSON data
curl -X POST https://api.example.com/users \
  -H "Content-Type: application/json" \
  -d '{"name":"John","email":"john@example.com"}'

# Include authentication header
curl -H "Authorization: Bearer YOUR_TOKEN" https://api.example.com/users

# Save response to file
curl https://api.example.com/users -o response.json

# Follow redirects
curl -L https://example.com

# Set timeout (seconds)
curl --max-time 10 https://api.example.com

# Show timing information (useful for latency debugging)
curl -w "@curl-format.txt" https://api.example.com
```

**Real-world production use case:**

API endpoint returns 401 Unauthorized. Is it the token, the header format, or the endpoint?

```bash
# Step 1: Test without auth (should fail)
curl -i https://api.example.com/users/123
# Output: 401 Unauthorized

# Step 2: Check if token format is correct
curl -i -H "Authorization: Bearer abc123def456" https://api.example.com/users/123

# Step 3: Compare successful vs failing calls
# Working call (from another service):
curl -i -H "Authorization: Bearer xyz789abc123" https://api.example.com/users/123
# Output: 200 OK

# Debugging: Is it the token validity or the header format?
curl -v -H "Authorization: Bearer abc123def456" https://api.example.com/users/123
# Shows: if server receives header correctly, server responds with error reason

# Response: 401 - Token expired (then regenerate token)
# Response: 401 - Invalid signature (then verify token generation)
# Response: 403 - Insufficient permissions (then check user role)
```

**Interview tip:** Mention that `curl -v` is your debugging toolΓÇöit shows exactly what's being sent and what's coming back.

---

#### `wget` - Download Files
**What it does:** Downloads files from web, useful for bulk downloads

```bash
# Basic download
wget https://example.com/file.zip

# Download and save with different name
wget https://example.com/file.zip -O myfile.zip

# Continue incomplete download
wget -c https://example.com/largefile.zip

# Download recursively (whole website)
wget -r https://example.com

# Set timeout
wget --timeout=10 https://example.com/file.zip

# With authentication
wget --user=username --password=password https://example.com/file.zip
```

**Production use case:**

Download logs from a production server for analysis:

```bash
# Download last hour of logs
wget https://logs-server.internal/api/logs?since=1hour -O logs.json

# Download multiple log chunks
for i in {1..5}; do
  wget https://logs-server.internal/logs/chunk_$i.log
done
```

---

#### `netstat` & `ss` - Network Connection Monitoring
**What it does:** Shows network connections, listening ports, statistics

```bash
# Show all listening ports
netstat -tuln
# t = tcp, u = udp, l = listening, n = numeric (no name resolution)

# Show all connections (listening + established)
netstat -tuan

# Show which process is using which port
netstat -tulnp
# p = show process PID and name

# Show only established connections
netstat -tuen

# Show statistics
netstat -s

# Count connections by state
netstat -an | grep ESTABLISHED | wc -l

# Modern alternative to netstat (faster, cleaner)
ss -tuln

# Show listening ports with process info
ss -tulnp

# Show all connections (established + waiting)
ss -tuan
```

**Real-world production use case:**

Port 3306 (MySQL) is not responding. Is MySQL listening?

```bash
# Check if MySQL is listening on port 3306
netstat -tulnp | grep 3306
# Output: tcp  0  0 127.0.0.1:3306  0.0.0.0:*  LISTEN  5432/mysqld

# Good! MySQL is listening on port 3306
# Problem might be: MySQL is only listening on localhost (127.0.0.1)
# If application is connecting from another server, it will fail!

# Solution: Configure MySQL to listen on all interfaces:
# Edit /etc/mysql/my.cnf:
# bind-address = 0.0.0.0

# Check how many connections are currently open
netstat -an | grep :3306 | grep ESTABLISHED | wc -l
# Output: 87

# That's 87 active database connections. Is it normal?
# Check max_connections setting in MySQL:
mysql -u root -p -e "SHOW VARIABLES LIKE 'max_connections';"
# If 87 is close to the limit, increase max_connections or fix connection leaks
```

---

#### `ping` - Test Network Connectivity
**What it does:** Sends packets to test if host is reachable

```bash
# Basic ping (press Ctrl+C to stop)
ping google.com

# Send specific number of packets
ping -c 5 google.com

# Set timeout per packet
ping -W 2000 google.com  # 2 second timeout

# Ping with timestamp
ping -D google.com

# Count received packets
ping -c 100 google.com | grep "packets received"
```

**Real-world production use case:**

Database server appears unresponsive. Is it a network issue or server is down?

```bash
# Step 1: Ping the database server
ping -c 5 db.internal.example.com
# Output: All 5 packets received = server is reachable

# Step 2: If ping fails
ping -c 5 db.internal.example.com
# Output: No packets received = network issue or server is down

# Investigate further
# - Check if firewall is blocking traffic
# - Check if server hardware is responding
# - Check network cables/connectivity
```

---

#### `ssh` - Secure Shell Remote Access
**What it does:** Securely connect to remote servers

```bash
# Basic SSH connection
ssh user@hostname

# SSH with specific port (default 22)
ssh -p 2222 user@hostname

# Execute command and exit
ssh user@hostname "ls -la"

# SSH with verbose output (for debugging connection issues)
ssh -v user@hostname

# Copy file to remote server (SCP)
scp file.txt user@hostname:/path/to/

# Copy file from remote server
scp user@hostname:/path/to/file.txt ./

# SSH tunneling (port forwarding)
# Forward local port 3306 to remote MySQL
ssh -L 3306:localhost:3306 user@hostname

# Keep connection alive (useful for long processes)
ssh -o ServerAliveInterval=60 user@hostname
```

**Real-world production use case:**

Can't connect to production database from your laptop. Database is on a private network.

```bash
# Step 1: SSH to the bastion/jumphost server
ssh -v user@bastion.example.com
# (This shows if there are SSH auth issues)

# Step 2: From bastion, test database connectivity
ssh user@bastion
mysql -u app -p -h db.internal "SELECT 1;" # Test database

# Step 3: From your laptop, tunnel through bastion
ssh -L 3306:db.internal:3306 user@bastion.example.com

# Now connect locally
mysql -u app -p -h 127.0.0.1
# It connects through the SSH tunnel to the remote database

# Debug SSH connection issues
ssh -v user@hostname 2>&1 | grep -i "auth\|error\|refused"
```

---

## SECTION 2: PROCESS DEBUGGING - CRITICAL FOR SUPPORT ENGINEERS

### 2.1 Is the Service Running?

**Scenario:** Application is down. First question: Is the process running?

```bash
# Method 1: Check if process exists
ps aux | grep "service-name"

# If you see the process line, it's running
# If you see only the grep line, it's NOT running:
# user   12345  0.0  0.0  2024  512 S+  10:45  0:00 grep service-name

# Method 2: Check if service is registered with systemd
systemctl status myservice

# Output if running:
# ΓùÅ myservice.service - My Application
#    Loaded: loaded
#    Active: active (running) since ...
#    PID: 5432

# Output if stopped:
# ΓùÅ myservice.service - My Application
#    Loaded: loaded
#    Active: inactive (dead) since ...

# Method 3: Check if process is listening on expected port
netstat -tulnp | grep "5000"
# If MySQL returns nothing, the process isn't listening

# Method 4: Check service logs for startup errors
journalctl -u myservice -n 50
# Shows last 50 lines of service logs

# Method 5: Try to start the service
systemctl start myservice
systemctl status myservice
```

**Decision tree:**
- Process exists + listening on port = Service is running correctly
- Process exists but NOT listening = Process crashed after startup
- Process doesn't exist = Service was never started or crashed

---

### 2.2 CPU & Memory Issues

#### Is the Process Using Too Much CPU?

```bash
# Show top CPU consumers
top -b -n 1 | head -12
# PID  USER %CPU %MEM COMMAND
# 1234 app  85.5  5.2 java -jar service.jar

# That's 85.5% CPU. Is this normal?

# Diagnose:
# 1. High CPU but low memory = CPU-bound work (processing, calculations)
# 2. High CPU and high memory = Memory leak (GC pressure)
# 3. Normal CPU but growing memory = Memory leak

# Real-time monitoring
watch -n 2 'ps aux | grep "java" | grep -v grep'

# Check CPU on all cores
cat /proc/cpuinfo | grep processor | wc -l
# If you have 4 cores, 100% on one core means 25% overall

# Solution depends on cause:
# - Slow query/infinite loop = Fix code
# - Too much traffic = Scale horizontally (add more servers)
# - Memory leak = Restart service (temporary) + fix code (permanent)
```

---

#### Is the Process Leaking Memory?

```bash
# Monitor memory growth over time
watch -n 30 'ps aux | grep service | grep -v grep'

# Run every 30 seconds for 5 minutes
# If RSS (memory) keeps growing: MEMORY LEAK

# Get memory details
ps aux | grep service | awk '{print $6}'  # Shows memory per line

# For Java apps, check garbage collection
jstat -gc -h 20 <PID> 1000  # Shows GC stats every second

# If heap keeps growing despite GC runs: memory leak in Java

# Check memory usage by percentage
free -m  # Shows total/used memory

# If memory is 90%+ used, something is wrong
# Check which process is responsible:
top -o %MEM | head -10

# Solution:
# 1. Short-term: Restart the service
# 2. Long-term: Fix the code causing the leak
# 3. Monitor: Add alerting for memory threshold
```

---

### 2.3 Permission Issues

```bash
# Service returns "Permission denied" error

# Check who owns the service
ps aux | grep service
# user app 5432 ...

# Check file permissions
ls -l /path/to/data/file
# -rw------- 1 root root  # Only root can read

# If service runs as 'app' user but file owned by 'root':
# SERVICE CAN'T READ FILE = Permission Denied

# Solution:
chown app:app /path/to/data/file
# OR
chmod 644 /path/to/data/file  # Make readable to all

# Verify fix
sudo -u app cat /path/to/data/file  # Should work now
```

---

### 2.4 Connection & Port Issues

```bash
# Service can't listen on port 8080

# Step 1: Is something else using that port?
netstat -tulnp | grep 8080
# tcp  0  0 0.0.0.0:8080  0.0.0.0:*  LISTEN  1234/nginx

# Yes! Nginx is using port 8080

# Options:
# A. Stop nginx if it's not needed
# B. Change service to different port
# C. Configure nginx as reverse proxy

# Step 2: Is port < 1024? (requires root)
# Ports 1-1024 are privileged
# If service is unprivileged user, it can't use port 80
# Solution: Run as root, or use port > 1024, or use reverse proxy

# Step 3: Is firewall blocking the port?
# If local machine works but remote doesn't:
sudo iptables -L | grep 8080
# If no rule for 8080: firewall is blocking it
# Solution: Open firewall port
sudo ufw allow 8080
```

---

## SECTION 3: NETWORKING BASICS FOR TROUBLESHOOTING

### 3.1 DNS - Domain Name System

**What it does:** Converts domain names (example.com) to IP addresses

```bash
# Resolve domain to IP
nslookup google.com
# Output: google.com has address 142.250.185.46

# Check specific nameserver
nslookup google.com 8.8.8.8  # Using Google's DNS

# More detailed DNS info
dig google.com

# Check which DNS server is configured
cat /etc/resolv.conf
# nameserver 8.8.8.8
# nameserver 8.8.4.4

# Check DNS TTL (time before re-resolve)
dig google.com | grep "google.com"
# google.com.  300  IN  A  142.250.185.46
# TTL=300 seconds means resolved IP is cached for 5 minutes
```

**Real-world production use case:**

API calls to external service fail with "Cannot resolve hostname"

```bash
# Step 1: Can you resolve the hostname?
nslookup api.external.com
# If no address returned: DNS issue

# Step 2: Which DNS server should you use?
nslookup api.external.com 8.8.8.8  # Google DNS
nslookup api.external.com 1.1.1.1  # Cloudflare DNS

# Step 3: Check /etc/resolv.conf
cat /etc/resolv.conf

# If using wrong DNS: update it
# Step 4: Verify DNS propagation
dig api.external.com +trace
# Shows the full DNS lookup chain

# Common causes:
# - DNS server is down
# - Hostname not registered
# - Wrong DNS server configured
# - DNS TTL not updated yet
```

---

### 3.2 HTTP Status Codes - Understand What They Mean

```
2xx Success Codes:
200 OK                          - Request successful, response included
201 Created                     - Resource created successfully
202 Accepted                    - Request accepted for processing
204 No Content                  - Success but no response body

3xx Redirect Codes:
301 Moved Permanently           - Resource moved to new URL
302 Found                       - Temporary redirect
304 Not Modified                - Client cache is current
307 Temporary Redirect          - Temporary redirect (same method)

4xx Client Error Codes:
400 Bad Request                 - Malformed request syntax
401 Unauthorized                - Authentication required
403 Forbidden                   - Authenticated but no permission
404 Not Found                   - Resource doesn't exist
405 Method Not Allowed          - GET allowed, but POST not allowed
409 Conflict                    - Request conflicts with resource state
429 Too Many Requests           - Rate limited

5xx Server Error Codes:
500 Internal Server Error       - Unexpected server error
502 Bad Gateway                 - Gateway/proxy received invalid response
503 Service Unavailable         - Server temporarily unavailable
504 Gateway Timeout             - Gateway didn't receive timely response
```

**Real-world interpretation:**

```bash
# Your API returns 502 Bad Gateway
# This means: The load balancer (nginx) can't reach your backend service

# Debug steps:
# 1. Is backend service running?
systemctl status backend-service
# 2. Is it listening on the right port?
netstat -tulnp | grep "8000"
# 3. Can the load balancer reach the backend?
curl -v http://backend-internal-ip:8000/health
# 4. Is there a firewall rule blocking traffic?
```

---

### 3.3 HTTPS & TLS/SSL

**What it does:** Encrypts HTTP traffic using certificates

```bash
# Check certificate validity
echo | openssl s_client -servername example.com -connect example.com:443 2>/dev/null | openssl x509 -noout -dates
# Output:
# notBefore=Jan 15 00:00:00 2023 GMT
# notAfter=Jan 14 23:59:59 2024 GMT

# If notAfter is in the past: CERTIFICATE EXPIRED = 403/SSL errors

# Check certificate details
openssl x509 -in /etc/ssl/certs/certificate.pem -text -noout

# Verify certificate chain
openssl s_client -connect example.com:443 -showcerts < /dev/null

# Check if certificate matches domain
openssl x509 -in cert.pem -text | grep Subject
# Should match the domain you're connecting to
```

**Real-world production use case:**

HTTPS connection fails with "certificate verification failed"

```bash
# Step 1: Is certificate expired?
curl -v https://api.example.com
# Output: SSL: CERTIFICATE_VERIFY_FAILED
# Possible cause: Certificate expired

# Step 2: Check expiration date
echo | openssl s_client -servername api.example.com -connect api.example.com:443 2>/dev/null | openssl x509 -noout -dates
# notAfter=May 20 2025 (certificate is valid)

# Step 3: Check if certificate matches domain
openssl x_client -connect api.example.com:443 -showcerts < /dev/null | grep subject
# Should show: subject=CN=api.example.com

# Common causes:
# - Certificate expired (renew immediately)
# - Wrong certificate (deployed to wrong server)
# - Hostname mismatch (certificate for *.example.com but you're connecting to api.example.com)
# - Certificate not trusted (self-signed, add to CA bundle)
```

---

### 3.4 REST APIs - How They Work

**REST = Representational State Transfer**

```
Basics:
- Uses HTTP methods: GET (read), POST (create), PUT (update), DELETE (delete)
- Uses HTTP status codes to indicate result
- Request/response in JSON format (usually)

Anatomy of REST API call:
GET /api/users/123 HTTP/1.1
Host: api.example.com
Authorization: Bearer token123
Content-Type: application/json

Response:
HTTP/1.1 200 OK
Content-Type: application/json
{
  "id": 123,
  "name": "John",
  "email": "john@example.com"
}
```

**Common API debug scenarios:**

```bash
# API returns 404 for a resource that exists
# Step 1: Verify the endpoint
curl -i GET https://api.example.com/api/users/123

# Step 2: Check if it's a typo in path
curl -i GET https://api.example.com/api/user/123  # singular vs plural?

# Step 3: Check if authentication is required
curl -i -H "Authorization: Bearer token" https://api.example.com/api/users/123

# API returns 401 Unauthorized
# Step 1: Is token provided?
curl -i https://api.example.com/users  # Without auth
# Returns 401: Yes, authentication required

# Step 2: Is token format correct?
curl -i -H "Authorization: Bearer mytoken" https://api.example.com/users
# vs
curl -i -H "X-API-Key: mytoken" https://api.example.com/users

# Step 3: Is token expired?
# Check token expiration date
jq -R 'split(".") | .[1] | @base64d | fromjson' <<< "your_jwt_token"

# API is slow (high latency)
# Measure latency breakdown
curl -w "@curl-format.txt" https://api.example.com/users

# Where's the time spent?
# - DNS lookup too slow? Check nameserver
# - Connection establishment slow? Check network/firewall
# - Server processing slow? Check server logs
# - Response transfer slow? Check payload size
```

---

### 3.5 Ports - Well-Known Services

```
Common ports:
21    FTP (File Transfer)
22    SSH (Secure Shell)
25    SMTP (Email)
53    DNS (Domain resolution)
80    HTTP (Web)
110   POP3 (Email)
143   IMAP (Email)
443   HTTPS (Secure Web)
3306  MySQL (Database)
5432  PostgreSQL (Database)
6379  Redis (Cache)
8000-8999  Common app/service ports
```

**Real-world use case:**

Service runs on port 8080 but clients can't reach it

```bash
# Step 1: Is service listening?
netstat -tulnp | grep 8080
# If nothing: service isn't listening or on wrong port

# Step 2: Is firewall allowing traffic?
# Test from another server
curl http://service-ip:8080/health

# If fails: firewall is blocking
sudo ufw allow 8080

# Step 3: Is port correctly configured in app?
# Check app config file
cat /etc/myapp/config.yml | grep port
# Should show: port: 8080

# If misconfigured, restart after fix
systemctl restart myapp
```

---

### 3.6 TCP/IP Basics - The Network Stack

```
Network layers (bottom to top):
1. Physical (cables)
2. Link (Ethernet, MAC addresses)
3. Network (IP addresses, routing)
4. Transport (TCP/UDP ports)
5. Application (HTTP, DNS, SSH)

When you curl https://api.example.com:443:

1. Resolve: DNS query to convert api.example.com ΓåÆ 192.168.1.100
2. Route: OS routing table finds network path to 192.168.1.100
3. ARP: Address Resolution Protocol finds MAC address of next hop
4. TCP: Establish connection to 192.168.1.100:443
5. TLS: Encrypt connection
6. HTTP: Send GET request
7. Receive: Response arrives
8. Decrypt: TLS decryption
9. Parse: HTTP parsing
10. Display: Show response
```

**Troubleshooting network issues:**

```bash
# Step 1: Can you reach the IP?
ping 192.168.1.100

# Step 2: Is it a DNS issue?
# With DNS:
curl https://api.example.com  # Slow

# Without DNS (use IP):
curl https://192.168.1.100    # Fast?
# If IP is fast but hostname is slow: DNS is the problem
# Solution: Check /etc/resolv.conf or update DNS cache

# Step 3: Is there a firewall/proxy blocking traffic?
curl -v https://api.example.com 2>&1 | grep -i "connected\|refused\|timeout"
# "Connection refused" = firewall or service down
# "Connection timeout" = network unreachable or slow

# Step 4: Check routing table
ip route show
# Should have a route to the destination network

# Step 5: Use traceroute to see path taken
traceroute api.example.com
# Shows each hop the packet takes
# If stops at certain hop: firewall/network issue there
```

---

### 3.7 Latency & Performance Debugging

**Scenario:** API calls are slow. Where's the bottleneck?

```bash
# Measure latency with curl
time curl https://api.example.com/users

# Real: 2.5s total time (too slow!)

# Detailed breakdown
curl -w "
  DNS: %{time_namelookup}
  Connect: %{time_connect}
  Pre-transfer: %{time_pretransfer}
  Start transfer: %{time_starttransfer}
  Total: %{time_total}
" https://api.example.com/users

# Output:
# DNS: 0.15s       (too slow - DNS issue?)
# Connect: 0.20s   (ok)
# Pre-transfer: 0.25s (TLS handshake - ok)
# Start transfer: 2.1s (server processing - SLOW!)
# Total: 2.3s

# Analysis: The server is slow, not the network
# Next step: Check server logs, database queries, CPU usage
```

---

### 3.8 Proxies & Load Balancers

```
Setup:
Client ΓåÆ Load Balancer ΓåÆ Backend Server 1
                       ΓåÆ Backend Server 2
                       ΓåÆ Backend Server 3

How to debug:
```

```bash
# Is traffic going through load balancer?
curl -v https://lb.example.com

# Check what headers load balancer adds
curl -i https://lb.example.com | grep -i "x-forwarded\|via"
# Output:
# X-Forwarded-For: 203.0.113.45 (client IP)
# Via: nginx/1.19.0 (reverse proxy info)

# Can you bypass load balancer? (test backend directly)
curl -v http://backend1.internal:8000/health
# If this works but LB doesn't, problem is in LB config

# Check backend server state
curl http://backend1.internal:8000/health
# Output: {"status": "up"}
curl http://backend2.internal:8000/health
# Output: {"status": "down"}

# So backend2 is down, LB should route around it
# Check LB config to ensure it detects failed backends
```

---

## SECTION 4: SCENARIO-BASED DEBUGGING - THE CRITICAL QUESTION

### "API is failing. How will you debug?" - Complete Walkthrough

This is THE question you'll be asked. Here's the expected answer:

```
Question: "Our API is returning 500 errors. How will you debug?"

Expected approach (score points with each step):
```

**Step 1: Confirm the problem**
```bash
# Try to reproduce the error
curl -i https://api.example.com/endpoint
# 500 Internal Server Error

# Is it consistent or intermittent?
for i in {1..10}; do curl -s -o /dev/null -w "%{http_code}\n" https://api.example.com/endpoint; done
# All 500? = Consistent (service is completely broken)
# Mixed 200/500? = Intermittent (specific conditions trigger it)
```

**Step 2: Check if service is running**
```bash
# Is the process running?
ps aux | grep "api-service"

# Is it listening on the right port?
netstat -tulnp | grep "8000"

# Can you reach the health endpoint?
curl -i http://localhost:8000/health
```

**Step 3: Check the logs**
```bash
# Last 50 lines of error logs
tail -n 50 /var/log/api/error.log

# Looking for:
# - Stack traces (show root cause)
# - Database connection errors
# - Memory/CPU issues
# - Dependency failures

# Watch logs in real-time while reproducing
tail -f /var/log/api/error.log
# Then trigger the error in another terminal
```

**Step 4: Analyze the error**
```bash
# If you see: "Database connection timeout"
# Next steps:
# - Check if database is running
# - Check if network can reach database
# - Check connection pool settings

# If you see: "Out of memory"
# Next steps:
# - Check memory usage: free -m
# - Identify which process: top
# - Restart if urgent, fix code permanently

# If you see: "External API returned 502"
# Next steps:
# - Check which external API: grep in logs
# - Verify that API is working
# - Check auth tokens/certificates
```

**Step 5: Check system resources**
```bash
# Is it a resource issue?
top -b -n 1 | head -15

# CPU maxed out?
# - Identify heavy process
# - Check for infinite loops in logs
# - Scale horizontally or fix code

# Memory maxed out?
# - Check for memory leaks (RSS keeps growing)
# - Restart service (temporary)
# - Fix code (permanent)

# Disk full?
# - Check disk space: df -h
# - Clean up old logs: rm /var/log/old/*.log
# - Or increase disk allocation
```

**Step 6: Check dependencies**
```bash
# Is database accessible?
mysql -u app -p -h db.example.com -e "SELECT 1;"

# Can you reach external APIs?
curl -i https://external-api.com/health

# Check authentication (tokens, API keys)
# Verify they're not expired or revoked
grep "token\|auth" /var/log/api/error.log

# Check network connectivity
ping db.example.com
netstat -an | grep "3306" | grep ESTABLISHED | wc -l
```

**Step 7: Reproduce with more detail**
```bash
# Get exact error details
curl -v https://api.example.com/endpoint 2>&1 | tee debug.log

# Add debug headers if API supports them
curl -H "X-Debug: true" https://api.example.com/endpoint

# Try with different params (is it a specific input?)
curl https://api.example.com/endpoint?id=123
curl https://api.example.com/endpoint?id=999

# Is one working and one failing?
```

**Step 8: Check recent changes**
```bash
# Did anything change recently?
# - Deployment/code changes
# - Configuration changes
# - Infrastructure changes

# Can you rollback?
git log --oneline -10
# If recent deploy looks suspicious, rollback and see if error goes away

# Check deployed version
curl https://api.example.com/version
# or check deployed code timestamp
ls -l /opt/api/app.jar
```

**Final diagnosis**
```
You've now tested:
Γ£ô Service is running
Γ£ô Logs show root cause
Γ£ô System resources aren't maxed
Γ£ô Dependencies are accessible
Γ£ô No network issues

Your diagnosis should be one of:
1. Database problem (fix database)
2. Memory leak (restart + fix code)
3. Code bug (deploy fix)
4. Configuration issue (update config)
5. Dependency failure (fix dependency)
6. Rate limiting (upgrade plan or fix code efficiency)
```

---

## SECTION 5: INTERVIEW QUESTIONS & EXPERT ANSWERS

### Q1: "Walk me through how you'd debug an API that's returning 500 errors intermittently."

**Strong Answer:**
"I'd follow a systematic approach:

1. **Reproduce the issue** - Is it consistent or intermittent? This matters because consistent failures suggest the service is down, while intermittent failures suggest specific conditions trigger the error.

2. **Check service health** - Verify the process is running with `ps aux`, check it's listening on the right port with `netstat`, and look at the last few lines of logs with `tail -f`.

3. **Examine logs in detail** - `tail -f` the error logs while reproducing the issue, watching for stack traces or meaningful error messages. Grep for specific patterns: `grep ERROR /var/log/app.log | tail -50`.

4. **Check dependencies** - Test database connectivity with `mysql -e 'SELECT 1'`, verify external APIs are accessible with `curl`, check authentication tokens.

5. **Monitor system resources** - If no errors in logs, might be resource-constrained. Run `top` to check CPU/memory, `df -h` for disk space.

6. **Correlate with timing** - Are errors happening at specific times? Run `grep '500' /var/log/app.log | awk '{print $1}' | uniq -c` to see if there's a pattern.

The key insight is that for intermittent issues, you often need to capture the exact error stateΓÇöthat's why `tail -f` to watch logs live is so valuable, and why correlating with time is crucial."

**Why this scores points:**
- Shows systematic thinking
- Mentions specific tools with correct flags
- Understands difference between consistent and intermittent failures
- Explains the "why" behind each step

---

### Q2: "A database connection is timing out. What's your debugging process?"

**Strong Answer:**
"Database timeout usually means one of three things: network can't reach the database, the database is overloaded, or there's a firewall blocking traffic.

**Step 1 - Network reachability:**
```bash
ping db.example.com  # Can you reach the host?
curl -v telnet://db.example.com:3306 2>&1 | grep Connected  # Can you connect to port?
```

**Step 2 - Is the database service running?**
```bash
# On the database server:
systemctl status mysql
netstat -tulnp | grep 3306
```

**Step 3 - Connection pool health:**
```bash
# How many connections are currently open?
netstat -an | grep :3306 | grep ESTABLISHED | wc -l

# What's the max_connections limit?
mysql -u app -p -e 'SHOW VARIABLES LIKE \"max_connections\";'

# If open connections Γëê max_connections, you've exhausted the pool
```

**Step 4 - Check query logs for slow queries:**
```bash
# Enable slow query log (if not already)
# Then: tail -f /var/log/mysql/slow.log
# Long-running queries lock resources and exhaust connection pools
```

**Step 5 - Application logs for connection errors:**
```bash
tail -f /var/log/app/error.log | grep -i 'database\|connection\|timeout'
```

The most common cause I've seen is exhausted connection pools due to slow queries or connection leaks in the application code. You can quickly identify this by comparing open connections to the max_connections limit."

**Why this scores points:**
- Explains the three root causes upfront
- Methodical debugging approach
- Includes specific commands with real outputs
- Shows understanding of connection pools
- Mentions application-level causes (code issues)

---

### Q3: "How would you identify which process is consuming all CPU resources?"

**Strong Answer:**
```bash
# Quick answer with top
top -b -n 1 | head -12

# Output:
# PID  USER  %CPU %MEM COMMAND
# 1234 app   85.2  4.5 java -jar service.jar

# That's clear: Java process is consuming 85% CPU.

# Dig deeper: Is this normal for your application?
# One-liner to compare all processes:
ps aux --sort=-%cpu | head -5

# For Java apps specifically, check what's causing the CPU usage:
jstat -gc -h 20 1234 1000  # Shows GC every second

# If Full GC is running constantly: memory leak
# If user time is high: application logic is compute-intensive
# If system time is high: I/O is causing CPU usage

# Monitor over time to see if it's sustained:
watch -n 5 'ps aux --sort=-%cpu | head -5'

# Once you identify the process, check logs:
tail -f /var/log/app.log | grep -i 'processing\|error\|timeout'

# Common causes:
# - Infinite loop (code bug)
# - Too many parallel operations (rate limiter needed)
# - Blocking I/O (async would help)
# - Memory pressure causing GC (increase heap or fix leak)

# For quick fix, restart the service:
systemctl restart app

# For permanent fix, analyze logs and optimize the code.
```

---

### Q4: "A service is failing to start with 'Permission denied'. How do you debug?"

**Strong Answer:**
"Permission denied usually means the service can't read a file it needs, or can't listen on a privileged port. Here's the debugging flow:

**Identify what's being denied:**
```bash
# Try to start and capture the error
systemctl start myservice
systemctl status myservice
# Shows: Failed to start because: Permission denied

# Get more details from the log
journalctl -u myservice -n 100
# Might show: Cannot read /etc/myservice/config.yml
```

**Check file permissions:**
```bash
ls -l /etc/myservice/config.yml
# Output: -rw------- 1 root root config.yml

# Who does the service run as?
cat /etc/systemd/system/myservice.service | grep User=
# Output: User=appuser

# Problem: File owned by root, readable only by root (mode 600)
# But service runs as 'appuser' user

# Solution: Change ownership or permissions
chown appuser:appuser /etc/myservice/config.yml
# OR
chmod 644 /etc/myservice/config.yml

# Verify the service can now read it:
sudo -u appuser cat /etc/myservice/config.yml
```

**Check for privileged port issue:**
```bash
# If service tries to listen on port < 1024:
grep Port /etc/myservice/config.yml
# Output: Port=80

# Port 80 requires root privileges
# If service runs as unprivileged user: Permission Denied

# Solutions:
# 1. Run service as root (less secure)
# 2. Change to port > 1024
# 3. Use iptables to forward port 80 to port 8080
```

**Check directory access:**
```bash
# Ensure service can write to its working directory
ls -ld /var/log/myservice/
# If directory is owned by root and service can't write: Permission Denied

# Fix:
chown appuser:appuser /var/log/myservice/
```

The key insight is that 'Permission denied' tells you which file is problematic, then it's just file permission fixing."

---

### Q5: "How do you monitor and alert on high CPU usage?"

**Strong Answer:**
"Monitoring high CPU is important because sustained high CPU means either the application is doing heavy work (normal) or something is wrong (slow query, infinite loop, etc.).

**Real-time monitoring:**
```bash
# Watch CPU every 5 seconds
watch -n 5 'top -b -n 1 | head -12'

# Or set up a script that alerts if CPU > 80%:
#!/bin/bash
while true; do
  cpu_usage=$(top -b -n 1 | grep "Cpu" | awk '{print $2}' | cut -d'%' -f1)
  if (( $(echo "$cpu_usage > 80" | bc -l) )); then
    echo "ALERT: CPU usage is ${cpu_usage}%"
    # Send alert email/slack
    curl -X POST https://hooks.slack.com/... -d "CPU Alert"
    # Identify the process
    top -b -n 1 | head -5
  fi
  sleep 60
done
```

**For production systems, use monitoring tools:**
```bash
# Prometheus (collect metrics)
# Grafana (visualize)
# AlertManager (send alerts)

# Query: Show CPU usage percentage
# Alert rule: If CPU > 80% for 5 minutes, send alert
```

**When you get the alert:**
```bash
# Step 1: Which process?
top -b -n 1 | sort -k 9 -r | head

# Step 2: Is it expected?
# If API server maxing CPU during peak traffic = expected
# If database is maxing CPU = investigate slow queries

# Step 3: Trending analysis
# Use sar or similar to see if CPU is steadily increasing (leak) or spikes (traffic)
sar -u 1 10  # Show CPU every 1 second, 10 times
```

---

### Q6: "Explain the difference between TCP vs UDP and when each is used."

**Strong Answer:**
"**TCP (Transmission Control Protocol):**
- Connection-oriented: must establish connection before sending data
- Reliable: guarantees data arrives in order
- Slower: confirms each packet
- Used for: HTTP/HTTPS, SSH, databases, anything that can't afford lost packets
- Example: Web browsing, email, API calls

```bash
# TCP connection to a service
curl https://api.example.com  # Uses TCP port 443 for HTTPS
telnet example.com 22         # TCP port 22 for SSH
```

**UDP (User Datagram Protocol):**
- Connectionless: just send data
- Unreliable: no guarantee data arrives
- Faster: no confirmation overhead
- Used for: DNS, streaming, gaming, anything where speed matters more than accuracy
- Example: Video streaming, online games, VoIP

**Real-world debugging:**

```bash
# TCP: Establish connection is slow
curl -v https://api.example.com
# If connection takes 5 seconds: network or server issue

# UDP: Can't debug easily because connectionless
# But DNS (UDP) is slow:
time nslookup google.com
# Takes 2 seconds: DNS server is slow, change nameserver

# See which protocol each port uses:
grep -E '^(80|443|53|22)' /etc/services
# 53/udp = DNS (UDP)
# 80/tcp = HTTP (TCP)
```

**For interviews, explain the tradeoff:**
TCP = Reliable but slower, UDP = Fast but unreliable. Choose based on requirements."

---

### Q7: "An application deployed 1 hour ago is now returning 404 errors. What do you check?"

**Strong Answer:**
"404 errors mean the requested resource doesn't exist. Since this started after a deployment, something in that deployment is broken.

**Step 1: Verify the endpoint exists:**
```bash
# Test the endpoint
curl -i https://api.example.com/api/users

# Is it really returning 404?
# 404 = Not Found
# 400 = Bad Request (try different params)
# 401 = Unauthorized (check token)
```

**Step 2: Check what changed in deployment:**
```bash
# What code was deployed?
git log --oneline -5
# 1abc234 Deploy v2.0
# 5def678 Fix user endpoint

# Did the code have this endpoint before?
git show 1abc234:src/api/users.py | grep "@app.route"

# What changed?
git diff HEAD~1 HEAD -- src/api/
```

**Step 3: Check if routing is broken:**
```bash
# If the new code has typos in the route definition:
# Old: @app.route('/api/users')
# New: @app.route('/api/user')  ΓåÉ Missing 's'

# Check the deployed code:
cat /opt/api/src/api/users.py | grep "route"

# Verify it matches what the client is calling
```

**Step 4: Check if service restarted properly:**
```bash
# When was the service restarted?
systemctl status myapi | grep "Active"
# If 1 hour ago = matches deployment time (good)

# Is it running the new code?
ps aux | grep java
# Check the jar file timestamp
ls -l /opt/api/app.jar

# Is it the new version?
curl https://api.example.com/version
# Should show v2.0
```

**Step 5: Check if configuration broke routing:**
```bash
# Did deployment change nginx config?
cat /etc/nginx/sites-enabled/api.conf | grep location
# If routing is misconfigured, requests go to wrong backend
```

**Step 6: Rollback if unsure:**
```bash
# Rollback to previous version
git revert HEAD
make deploy

# Verify 404 goes away
curl https://api.example.com/api/users
# Should return 200 now

# Then investigate what broke in the new code
```

**This shows:** You understand deployment, routing, versioning, and how to quickly identify if code change broke something."

---

### Q8: "How would you debug network latency between two services?"

**Strong Answer:**
```bash
# Measure round-trip latency
ping service2.internal

# Ping shows ICMP latency, but actual app latency might be different
# Use curl to measure application latency:
time curl https://service2.internal/health

# Breakdown latency with curl:
curl -w "@curl-format.txt" https://service2.internal/endpoint

# Output breakdown:
# DNS lookup:        0.015s ΓåÉ Slow DNS?
# TCP connect:       0.025s ΓåÉ Network latency
# TLS handshake:     0.040s ΓåÉ Crypto overhead
# Server processing: 1.200s ΓåÉ SERVER IS SLOW (not network)
# Transfer:          0.020s ΓåÉ Size/bandwidth

# If server processing is slow:
# - Check service logs for slow queries
# - Check service CPU/memory
# - Check database response time

# If DNS lookup is slow:
# nslookup service2.internal
# Try different DNS: nslookup service2.internal 8.8.8.8
# Or use IP directly: curl https://10.0.1.50

# If TCP connect is slow:
# - Network is congested
# - Firewall processing delay
# - Route has many hops: traceroute service2.internal

# For sustained monitoring:
ab -c 10 -n 100 https://service2.internal/endpoint
# Shows average response time and percentiles

# Or use wrk for more detailed metrics:
wrk -c 100 -d 30s https://service2.internal/endpoint
```

---

### Q9: "What's the difference between 502 Bad Gateway and 503 Service Unavailable?"

**Strong Answer:**
"**502 Bad Gateway:**
- Load balancer/reverse proxy can't reach backend service
- Backend service is unreachable (down, crashed, or firewall blocking)
- Load balancer is running, but backend is not

```bash
# Debugging 502:
# 1. Is backend service running?
ssh backend-server
systemctl status myservice

# 2. Is it listening on the right port?
netstat -tulnp | grep 8000

# 3. Can load balancer reach it?
curl http://backend-internal-ip:8000/health

# 4. Check firewall between LB and backend
# If local curl works but remote fails: firewall
```

**503 Service Unavailable:**
- Service is intentionally temporarily unavailable
- Too many requests (rate limited)
- Service is overloaded (max connections reached)
- Service marked itself as 'unhealthy'

```bash
# Debugging 503:
# 1. Is service running?
systemctl status myservice  # Should be running

# 2. Is it overloaded?
top  # Check CPU/memory
netstat -an | grep ESTABLISHED | wc -l  # Connection count

# 3. Check service logs for error threshold
tail -f /var/log/myservice.log | grep 'unhealthy\|overload'

# 4. Are rate limits being hit?
grep '503' /var/log/access.log | wc -l

# 5. Check max connections limit
mysql -e 'SHOW VARIABLES LIKE \"max_connections\";'
netstat -an | grep ESTABLISHED | wc -l  # Current connections
```

**Quick diagnostic:**
- 502 = Backend problem (service down/unreachable)
- 503 = Frontend problem (service overloaded/throttling)

For interviews: Mention that 502 requires checking backend, while 503 requires checking load/limits."

---

### Q10: "Walk through debugging an SSH connection that's failing."

**Strong Answer:**
```bash
# First, try to connect with verbose output
ssh -v user@hostname
# Output shows: key attempt, auth methods, connection failures

# Common issues and how to diagnose:

# Issue 1: "Connection refused"
ssh -v user@hostname
# Output: Connection refused on port 22

# Debug:
# - Is SSH service running on server?
ssh user@hostname 'systemctl status ssh'
# - Is SSH listening on port 22?
netstat -tulnp | grep 22

# Issue 2: "Permission denied (publickey)"
# Public key auth failed

ssh -v user@hostname
# Shows: Trying public key authentication... Denied

# Debug:
# - Is your public key on server?
ssh user@hostname 'cat ~/.ssh/authorized_keys' | grep your-key
# - Wrong key format?
# Regenerate keys: ssh-keygen -t rsa

# Issue 3: "Connection timed out"
ssh -v user@hostname
# Output: Connection timed out

# Debug:
# - Can you reach the host?
ping hostname
# - Firewall blocking port 22?
# Test from another host: ssh user@hostname from different network
# - Is there a proxy/bastion?
ssh -v user@bastion hostname

# Issue 4: "Unknown host key"
# First time connecting to a new server

ssh -v user@hostname
# Output: Unknown host key. Continue? (yes/no)

# Debug:
# - This is expected for first connection
# Type 'yes' to add to known_hosts
# - If key changes: possible MITM attack
# Run: ssh-keyscan -H hostname >> ~/.ssh/known_hosts

# Most detailed debugging:
ssh -vvv user@hostname 2>&1 | tee ssh_debug.log
# vvv = maximum verbosity
# Shows: key attempts, auth methods, encryption details
```

**For interview:** Emphasize that `ssh -v` shows you exactly what's happening, and methodically testing each step (ping, port open, auth) narrows down the issue.

---

### Q11: "Describe how you'd locate a memory leak in a running application."

**Strong Answer:**
```bash
# Step 1: Confirm memory is growing
# Monitor memory usage over time
watch -n 60 'ps aux | grep appname | grep -v grep | awk "{print \$6}"'

# If RSS (memory) keeps growing every 60 seconds: MEMORY LEAK

# Step 2: Identify the process
ps aux | sort -k 6 -rn | head

# Step 3: For Java apps, analyze heap
# Get PID
PID=$(pgrep -f 'java.*myapp')

# Dump heap
jmap -dump:live,format=b,file=heap.bin $PID

# Analyze what's taking memory
jhat -J-Xmx2g heap.bin
# Browser to http://localhost:7000

# Look for large object arrays or strings that shouldn't exist

# Step 4: For other languages, use profilers
# Python: memory_profiler
# Go: pprof

# Step 5: Find which code is leaking memory
# Enable debug logging
# grep logs for patterns before memory spikes
grep -B 10 'memory.*exceeded' /var/log/app.log

# Step 6: Common causes to check
# - Database connections not closed
# - File handles not closed
# - Cache growing unbounded
# - Event listeners not unregistered

# Temporary fix (quick)
# Restart the service every night (cron job)
echo '0 2 * * * systemctl restart myapp' | crontab -

# Permanent fix
# Find the leak in code and close/release resources properly
```

---

### Q12: "A critical API is in a degraded state. Give me your incident response steps."

**Strong Answer - Incident Response Playbook:**

```
1. ASSESS THE SITUATION (< 1 minute)
- Is it completely down or partially degraded?
- How many users affected?
- How critical is it?
- Should you trigger incident response (page ops team)?

Commands:
curl -i https://api.example.com/health  # Service responding?
curl https://api.example.com/endpoint   # Returning errors?
```

```
2. GATHER DATA (< 2 minutes)
- Check error rates: tail -f /var/log/api.log | grep ERROR | wc -l
- Check response times: tail -f /var/log/api.log | grep duration | awk '{print $NF}' | sort -rn | head
- Check which endpoints are broken: tail -f /var/log/api.log | grep ERROR | grep -o 'POST /api/[^ ]*' | uniq -c

Commands:
ps aux | grep apiprocess  # Process running?
top -b -n 1 | head -12    # Resources normal?
netstat -an | grep ESTABLISHED | wc -l  # Connection count normal?
```

```
3. CHECK RECENT CHANGES (< 2 minutes)
- Was there a recent deployment?
- Did database configuration change?
- Was there a scaling event?

Commands:
git log --oneline -5  # Recent commits?
ls -l /opt/api/app.jar | awk '{print $6, $7, $8}'  # Deployment time?
systemctl status apiservice | grep Active  # Recent restart?
```

```
4. ISOLATE THE ISSUE (< 5 minutes)
- Database issue? Try: mysql -e 'SELECT 1;'
- Memory issue? Check: free -m
- CPU issue? Check: top
- Network issue? Try: ping external.api.com

Commands:
tail -n 100 /var/log/api.log | grep -i 'error\|exception' | tail -20
grep 'database\|connection\|timeout' /var/log/api.log | tail -10
```

```
5. IMPLEMENT QUICK FIX (< 5 minutes)
If obvious issue (process crashed):
systemctl restart apiservice

If database connection exhausted:
# Restart connection pool or database

If memory/CPU issue:
# Identify culprit, consider kill -9 if truly urgent

If recent deployment is suspect:
git revert HEAD
make deploy-rollback
```

```
6. VERIFY FIX (< 2 minutes)
curl -i https://api.example.com/endpoint  # Returns 200?
for i in {1..10}; do curl -s -w '%{http_code}\n' https://api.example.com/endpoint; done  # Consistent success?

Check error rate dropping:
tail -f /var/log/api.log | grep ERROR | wc -l  # Should be 0 or very low
```

```
7. COMMUNICATE (ongoing)
- Update incident channel every 5-10 minutes
- Explain impact, root cause, solution
- Give ETA for full resolution

8. POST-INCIDENT (after resolution)
- Write RCA (Root Cause Analysis)
- Implement long-term fix
- Add monitoring to prevent recurrence
- Update runbooks for this scenario
```

**This shows:**
- Calm, methodical approach under pressure
- Prioritizes data gathering
- Quick wins (restart) followed by investigation
- Communication is critical
- Thinks about prevention (monitoring, runbooks)

---

## SECTION 6: PRODUCTION TROUBLESHOOTING CHEAT SHEET

### Quick Reference Commands

```bash
# Is service running?
ps aux | grep servicename
systemctl status servicename

# Check logs
tail -f /var/log/servicename/app.log
grep ERROR /var/log/servicename/*.log | tail -20

# Check port
netstat -tulnp | grep 8080

# Check resources
top -b -n 1 | head -15
free -m
df -h

# Check network
ping example.com
curl -i https://api.example.com
curl -v https://api.example.com

# Check database
mysql -u user -p -h host -e "SELECT 1;"
psql -U user -h host -c "SELECT 1;"

# Check system
uptime
w
uname -a
cat /proc/cpuinfo

# Monitor live
watch -n 5 'ps aux | grep servicename'
tail -f /var/log/servicename/*.log
top

# Process management
ps aux --sort=-%cpu | head
ps aux --sort=-%mem | head
kill -9 PID
systemctl restart servicename
```

---

## SECTION 7: FINAL INTERVIEW TIPS

### Do's
Γ£à Show step-by-step thinking
Γ£à Use specific command syntax  
Γ£à Explain why you're running each command
Γ£à Show knowledge of tool combinations (grep + awk + sort)
Γ£à Mention you'd check logs first
Γ£à Explain what normal looks like vs abnormal
Γ£à Always verify after making a change
Γ£à Think about trade-offs (quick fix vs proper fix)
Γ£à Mention monitoring/prevention for future

### Don'ts
Γ¥î Don't run commands without explaining them
Γ¥î Don't randomly restart services without investigation
Γ¥î Don't ignore logs and jump to system resources
Γ¥î Don't make assumptions without verification
Γ¥î Don't use kill -9 as first resort
Γ¥î Don't change multiple things at once
Γ¥î Don't forget to check authentication/tokens
Γ¥î Don't skip rollback consideration

### Key Phrases to Use
- "Let me verify..."
- "I'd check the logs first..."
- "Is this expected behavior or abnormal..."
- "I'd monitor this metric..."
- "The root cause appears to be..."
- "Let me test this hypothesis..."
- "I'd set up alerts for..."

---

## SECTION 8: REAL-WORLD SCENARIO EXERCISES

### Scenario 1: API Slow Degradation
*Your monitoring alerts that API response times increased from 200ms to 2000ms over 30 minutes*

Debug path:
```bash
# Check if traffic increased
grep -o "200\|500\|400" /var/log/access.log | sort | uniq -c | tail -3

# Check if specific endpoints are slow
tail -n 500 /var/log/access.log | awk '{print $(NF-6), $NF}' | sort -k2 -rn | head

# Check database query times
tail -f /var/log/mysql/slow.log

# Check memory growth
watch -n 10 'ps aux | grep app | grep -v grep | awk "{print \$6}"'

# Check if garbage collection is running constantly
jstat -gc -h 20 PID 1000

# Root cause likely: One slow query, database connections exhausted, or memory pressure
```

### Scenario 2: Intermittent Connection Timeouts
*Clients report random "connection timeout" errors, but not consistently*

Debug path:
```bash
# Check connection pool exhaustion
netstat -an | grep ESTABLISHED | wc -l
mysql -e 'SHOW VARIABLES LIKE "max_connections";'

# Check timeout configuration
grep -i timeout /etc/app/config.yml

# Check if slow queries are blocking connections
mysql -e 'SHOW FULL PROCESSLIST;' | grep Sleep

# Check application logs for pattern
grep -B 5 -A 5 "timeout" /var/log/app.log | head -30

# Root cause likely: DB connection pool too small, slow queries blocking, or incorrect timeout settings
```

### Scenario 3: Mysterious 403 Forbidden Errors
*Some users get 403, others work fine. Same endpoint.*

Debug path:
```bash
# Check what's in logs when user reports 403
grep 403 /var/log/access.log | tail -5

# See request details
tail -f /var/log/access.log | grep 403

# Check authorization header
curl -v -H "Authorization: Bearer token123" https://api.example.com/users

# Compare working vs non-working users
grep "user123" /var/log/access.log | grep 403 | wc -l
grep "user456" /var/log/access.log | grep 403 | wc -l

# Check permission rules
grep "403\|authorization\|permission" /var/log/app.log

# Root cause likely: User role/permissions issue, token expiration, or rate limiting by user
```

---

## FINAL SUMMARY

**The three things that will make or break your interview:**

1. **Know the troubleshooting flow:** Logs first, then system resources, then dependencies. Always verify each step.

2. **Command proficiency:** Be comfortable with `tail -f`, `grep`, `ps aux`, `netstat`, and `curl -v`. These are your weapons.

3. **Systematic thinking:** When asked to debug something, outline your approach first, then execute. Show you're methodical, not random.

**Practice these scenarios until they're muscle memory:**
- Service won't start ΓåÆ Check logs ΓåÆ Check permissions ΓåÆ Check port
- API returning errors ΓåÆ tail -f logs ΓåÆ Identify pattern ΓåÆ Check dependency
- System slow ΓåÆ top ΓåÆ Identify process ΓåÆ Check logs ΓåÆ Determine action

Good luck with your interview! The support engineer role rewards methodical thinkers who aren't afraid to dive into logs and use Linux tools effectively.

