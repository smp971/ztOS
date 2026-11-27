/* Private backend only; no display outputs, seat or phone device access. */
#define main ztmetro_main
#include "../ztmetro.c"
#undef main
#include <assert.h>
#include <wlr/backend/headless.h>

int main(void) {
    for (int attached = 0; attached < 4; attached++) {
        struct zt_server s = {0};
        s.wl_display = wl_display_create();
        assert(s.wl_display);
        s.backend = wlr_headless_backend_create(wl_display_get_event_loop(s.wl_display));
        assert(s.backend);
        if (attached & 1) {
            s.new_output.notify = server_new_output;
            wl_signal_add(&s.backend->events.new_output, &s.new_output);
        }
        if (attached & 2) {
            s.new_input.notify = server_new_input;
            wl_signal_add(&s.backend->events.new_input, &s.new_input);
        }
        destroy_backend(&s);
        assert(!s.backend);
        wl_display_destroy(s.wl_display);
    }
    puts("Backend cleanup: early failure and normal listener teardown passed.");
    return 0;
}
