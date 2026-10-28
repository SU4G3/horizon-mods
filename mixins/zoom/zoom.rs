// The zoom in effect, unless another mod's came first.
fn zoom_view(zoom: &mut Option<crate::game::native_hooks::NativeZoom>) {
    if zoom.is_none()
        && let Some((factor, smooth, turn)) = crate::game::official_zoom::view()
    {
        *zoom = Some(crate::game::native_hooks::NativeZoom {
            factor,
            smooth,
            turn,
        });
    }
}
