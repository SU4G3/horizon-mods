// While the key is held, the wheel zooms instead of moving the hotbar.
fn zoom_wheel(steps: f32, claimed: &mut bool) {
    if crate::game::official_zoom::wheel(steps) {
        *claimed = true;
    }
}
