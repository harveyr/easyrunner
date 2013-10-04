easyrunner
==========

This is a script to help deal with annoying test suites.

### Status
Working, but work in progress.

### What It Does

1. *Test Discovery.* It will search your test directory structure and find all test files matching the search string.
2. *Test Tracking.* It will run the discovered tests and progressively report what has passed and what has failed. 

### Why
This was originally (and hurriedly) written for a girthy Selenium test suite that took forever to run. Since the test runner (Behat) spammed the console as the tests ran, it was tough to tell what had failed unless you watched the log closely.

If you kick off the suite with this script, it will let you know on a glance what has failed and how many tests are left.

### Do You Want It?
Probably not, yet. I cobbled it together for a particular project, and I've only minimally tried to make it more reusable. It takes a bit of legwork to get it going.

Also, it's less useful to the extent:

1. your test suite runs quickly,
2. your test directory structure is shallow, or
2. you're using something like nosetests that does a good job reporting test progress.


Disclaimer: There's probably some ugly Python in here. Some of this code is old. I'll clean it up when I can spare the time.
