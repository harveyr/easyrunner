easyrunner
==========

This is a script to help deal with annoying test suites.

*Note:* The virtualenv requirements are just for tests.py. You don't need virtualenv for the script itself.

### Status
Working, but work in progress.

---

### What It Does

#### 1. Test Discovery

It will search your test directory structure and find all test files matching the search string.

For example, it turns this:

`> bin/behat features/applicationLms/modules/performance/performanceTableDimensions.feature --tags test1`

into this:

`> ./runner.py dimens @test1`

#### 2. Test Tracking

It will run the discovered tests and progressively report what has passed and what has failed. (Screenshot forthcoming, maybe.)

---

### Why
This was originally (and hurriedly) written for a girthy Selenium test suite that took eons to run. Since the test runner (Behat) spammed the console as the tests ran, it was tough to tell what had failed unless you watched the log closely.

Plus, the directory structure was complex enough that just finding a test became a distraction. (See example above.)

If you kick off the suite with this script, it will let you know on a glance what has failed and how many tests are left.

Or, if you're running a subset of tests, you can quickly target them with a search string.

It's a great help for this particular test suite. Not sure how necessary it is for other types of tests.

---

### Do You Want It?
Probably not, yet. I cobbled it together for a particular project, and I've only minimally tried to make it more reusable. It takes a bit of legwork to get it going.

Also, it's less useful to the extent:

1. your test suite runs quickly,
2. your test directory structure is shallow, or
2. you're using something like nosetests that does a good job reporting test progress.

---

### See Also

For faster (i.e., non-browser-automated) tests, I don't use this.

Instead, if I'm running individual test methods, I use something like my [SublimeRunnyNose](https://github.com/harveyr/SublimeRunnyNose) plugin to run them straight from my editor. Much preferred.

---

Disclaimer: There's probably some ugly Python in here. Some of this code is old. I'll clean it up when I can spare the time.
