# STEP viewer and revisions

The side window lets users inspect the generated model while the conversation manages the project. It contains a file header, STEP download, collapsed physical-part tree, view controls, and native construction playback when saved checkpoints exist.

## Drive the viewer

Use an owned instance and a real accepted artifact. Record source job, revision, STEP hash, and whether the case was newly built or copied solely as a display fixture.

- Open `?job=<id>` or call `show_assembly(id)`. Require model rendering, current revision, and a guarded `#download-step` link. Empty or evidence-blocked jobs have no enabled STEP download and point the user back to the conversation.
- Open `#open-tree`, select a `.tree-item`, and pick the visible geometry. Compare physical identity, highlight, isolation, and clearing. `#fit` frames the object; resizing preserves orbit direction. Multiple physical parts may expose `#explode` and `#explode-amount`. One-part checkpoints do not create an exploded assembly.
- For native checkpoints, use `#checkpoint-play`, `#checkpoint-scrubber`, `#checkpoint-label`, and `#checkpoint-final`. Seek actual saved meshes, pause across two observations, and return to the final model. Download remains bound to the accepted final STEP regardless of displayed checkpoint.
- Keep a ready viewer open. Use the agent's actual tools to save context, capture a request, and execute a supported CAD edit. Require automatic arrival of the new accepted revision without a reload. Context-only changes must not refetch or rebuild the mesh.
- During construction, distinguish the last accepted model from pending output. Download is gated until the service accepts a current result. A failed edit may retain the prior STEP, clearly identified as the previous result.
- Switch jobs or revisions while preview/checkpoint reads are delayed. Require late responses to lose ownership. Hide the page and verify polling pauses; visible return resumes current-job refresh.
- At desktop and 390×844, check canvas framing, readable file title, focus, enabled/disabled controls, timeline access, no horizontal overflow, and absence of authoring panels.

Use real controls and read-only DOM observations. Do not set internal state or call rendering functions as user-action proof. Controlled host/async tests supplement browser driving. Real ChatGPT rendering remains a separate gate from local HTTP and SDK stubs.

The separate printer study retains its own controls and historical source-CAD scope. Its animation does not prove reconstruction or native feature recovery.
