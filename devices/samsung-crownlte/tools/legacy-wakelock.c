/* LHD-only compatibility for Android 17 without Android SystemSuspend.
 * crown-sensorhub.service MUST hold a Linux sleep inhibitor while this is
 * loaded. These functions do not implement suspend-safe Android wake locks.
 * Never install this library in the system/vendor library directories.
 */
int acquire_wake_lock(int lock, const char *name)
{
    (void)lock;
    (void)name;
    return 0;
}

int release_wake_lock(const char *name)
{
    (void)name;
    return 0;
}
