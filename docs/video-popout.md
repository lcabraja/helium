# Video pop-out

Hover over an HTML5 video and click the small blue **Pop out video** button
in its upper-right corner. The video opens in Chromium's native floating
picture-in-picture window. The window has no standard frame, stays above other
windows, and preserves the video's aspect ratio when resized. Its controls
appear on hover. Use the return control or click the page button again to return
the video to its tab.

Playback and the site's session remain in the source tab. Closing that tab
closes its picture-in-picture window. Chromium supports one video pop-out at
a time. Portrait videos keep their portrait aspect ratio.

The bundled `helium_video_popout` component adds the button in an isolated
content-script world in each frame. It handles dynamically inserted videos,
custom player overlays and open shadow roots. It makes no network requests,
stores no data, and needs no background process. Its style lives in a closed
shadow root so page styles do not change the button. Only a trusted click can
open the floating window.

The button appears after video metadata is available. It respects a player's
`disablePictureInPicture` flag and iframe Permissions Policy. Audio-only media,
videos behind unrelated dialogs, closed shadow roots, and pages where content
scripts cannot run do not get a hover button. The existing video context-menu
picture-in-picture action remains available where supported.

## Verification

The supplemental `docs/macos-development-cpp-tests.patch` adds
`HeliumVideoPopoutBrowserTest` to `helium_development_tests`. Tests exercise the
actual bundled component with dynamically created video, trusted mouse input,
native picture-in-picture entry and exit, disabled and removed players,
custom controls, modal occlusion, scrolling, open shadow roots with a strict
style policy, and embedded frames.

Run the focused suite from the prepared build directory:

```sh
out/Default/helium_development_tests \
  --gtest_filter='HeliumVideoPopoutBrowserTest.*' \
  --test-launcher-jobs=1 --test-launcher-retry-limit=0 --use-mock-keychain
```

Also check a normal and a portrait media file in the native app. Pop each out,
resize the window, return it to its tab, and repeat with a custom player and an
embedded player. Use a disposable profile for manual development tests.
