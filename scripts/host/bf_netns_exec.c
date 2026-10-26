/* bf_netns_exec: enter the bf_engine network namespace and exec a command
 * as the calling user. Setuid-root only for setns(CLONE_NEWNET); the
 * namespace name is HARDCODED to bf_engine, and privileges are dropped
 * back to the caller before exec. fds are inherited untouched (Playwright
 * needs fd 3/4), unlike sudo-rs which closes fd 3+.
 *
 * MUST BE LINKED STATIC (-static): after setresuid the dynamic interpreter
 * is unavailable, and a dynamic binary dies with execvp ENOENT before ever
 * reaching the target. Build: gcc -static -O2 -o bf_netns_exec bf_netns_exec.c
 * Install: sudo install -o root -g root -m 4755 bf_netns_exec /usr/local/bin/ */
#define _GNU_SOURCE
#include <sched.h>
#include <unistd.h>
#include <stdio.h>
#include <fcntl.h>

#define NS_NAME "bf_engine"

int main(int argc, char *argv[]) {
    if (argc < 2) { fprintf(stderr, "usage: %s <command> [args...]\n", argv[0]); return 2; }
    int fd = open("/var/run/netns/" NS_NAME, O_RDONLY | O_CLOEXEC);
    if (fd < 0) { perror("open netns"); return 1; }
    if (setns(fd, CLONE_NEWNET) < 0) { perror("setns"); return 1; }
    close(fd);
    uid_t uid = getuid(); gid_t gid = getgid();
    if (setresgid(gid, gid, gid) < 0) { perror("setresgid"); return 1; }
    if (setresuid(uid, uid, uid) < 0) { perror("setresuid"); return 1; }
    execv(argv[1], &argv[1]);  /* absolute path; execvp dies ENOENT post-setuid */
    perror("execv");
    return 1;
}
