/* SPDX-License-Identifier: GPL-2.0-only */
/* Final syscall after the Crown exit ramfs has detached its filesystems. */
#include <errno.h>
#include <linux/reboot.h>
#include <stdio.h>
#include <string.h>
#include <sys/syscall.h>
#include <unistd.h>

int main(int argc, char **argv) {
    unsigned int command;
    const char *parameter = argc > 2 ? argv[2] : "";
    if (argc > 1 && !strcmp(argv[1], "--help")) {
        puts("crown-power reboot|poweroff|halt|kexec [reboot-parameter]; PID 1 only");
        return 0;
    }
    if (getpid() != 1 || argc < 2) {
        fputs("crown-power requires shutdown PID 1 and an explicit verb\n", stderr);
        return 1;
    }
    if (!strcmp(argv[1], "reboot"))
        command = *parameter ? LINUX_REBOOT_CMD_RESTART2 : LINUX_REBOOT_CMD_RESTART;
    else if (!strcmp(argv[1], "poweroff")) command = LINUX_REBOOT_CMD_POWER_OFF;
    else if (!strcmp(argv[1], "halt")) command = LINUX_REBOOT_CMD_HALT;
    else if (!strcmp(argv[1], "kexec")) command = LINUX_REBOOT_CMD_KEXEC;
    else { fputs("unknown shutdown verb\n", stderr); return 1; }
    sync();
    syscall(SYS_reboot, LINUX_REBOOT_MAGIC1, LINUX_REBOOT_MAGIC2, command, parameter);
    fprintf(stderr, "final power syscall: %s\n", strerror(errno));
    return 1;
}
