<script>
    import X from "@lucide/svelte/icons/x";

    export let open = false;

    let dialog;

    $: if (dialog) {
        if (open) dialog.showModal();
        else dialog.close();
    }

    function close() {
        open = false;
    }

    function handleBackdropClick(e) {
        if (e.target === dialog) close();
    }
</script>

<!-- svelte-ignore a11y-no-noninteractive-element-interactions -->
<dialog bind:this={dialog} on:click={handleBackdropClick} on:close={close}>
    <div class="help-container">
        <div class="help-header">
            <h2>Chapter Search</h2>
            <button class="close-btn" on:click={close} aria-label="Close"
                ><X size="20" /></button
            >
        </div>
        <div class="help-body">
            <p>
                Chapter Search scans the selected library to find books whose
                chapters match rules you define. This makes it easy to discover
                books that need better chapters, e.g. books with no chapters,
                books without an intro chapter, books where all chapters are
                just numbers, etc.
            </p>

            <h3>How it works</h3>
            <ol>
                <li>Choose a library and configure your search rules.</li>
                <li>
                    Click <strong>Search</strong>. achew will sync the chapter
                    data from Audiobookshelf and evaluate every book against
                    your rules.
                </li>
                <li>
                    Review the matched books. Click any book to see its chapter
                    list.
                </li>
                <li>
                    Click <strong>Start</strong> to begin processing that book,
                    or <strong>Ignore</strong> to hide it from future results.
                </li>
            </ol>

            <h3>Rules and rule sets</h3>
            <p>
                <strong>Rules</strong> are individual checks against a book's chapters
                (e.g., "chapter count is less than 3"). A rule requires a target
                ("Chapter count") and one or more conditions ("is less than 3").
            </p>
            <p>
                <strong>Rule sets</strong> allow you to group rules together and
                can either <em>Match Any</em>
                or <em>Match All</em> of the grouped rules. You can nest rule sets
                inside each other for arbitrarily complex conditions. Rules and rule
                sets can be individually enabled or disabled without deleting them.
            </p>

            <h3>Fuzzy matching</h3>
            <p>
                Conditions that are phrased as <em>"similar"</em> or
                <em>"similar to"</em> use fuzzy text comparison and are always case-insensitive.
                They match text that is significantly similar to the provided value
                and can be useful for finding chapters that closely resemble a phrase
                or book title.
            </p>

            <h3>Syncing chapter data</h3>
            <p>
                For the sake of speed and efficiency, a library's chapter data
                is fully synced to achew the first time that library is
                searched. While this can take several minutes for large
                libraries, it allows subsequent searches to be much faster.
            </p>
            <p>
                This synced data will always be updated with any changes you
                make to your books through achew. However, be aware that there
                is currently no way to effectively track external chapter
                changes. If you edit a book's chapters through another tool or
                directly in Audiobookshelf, achew's synced data will be out of
                date and search results might be inaccurate. As a workaround, you
                have two options:
            </p>
            <ul>
                <li>
                    In the search page below the rule section, clicking the <strong
                        >Clear Cache</strong
                    > button will force a full re-sync on the next search.
                </li>
                <li>
                    In the search results, clicking the refresh icon will fully
                    re-sync only the books in the results list.
                </li>
            </ul>
        </div>
    </div>
</dialog>

<style>
    dialog {
        padding: 0;
        border: none;
        border-radius: 12px;
        background: transparent;
        max-width: 90vw;
        max-height: 90vh;
        width: 680px;
    }

    dialog::backdrop {
        background: rgba(0, 0, 0, 0.6);
        backdrop-filter: blur(2px);
    }

    .help-container {
        background: var(--bg-primary);
        border-radius: 12px;
        border: 1px solid var(--border-color);
        display: flex;
        flex-direction: column;
        max-height: 85vh;
    }

    .help-header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        padding: 1.25rem 1.5rem;
        border-bottom: 1px solid var(--border-color);
    }

    .help-header h2 {
        margin: 0;
        font-size: 1.25rem;
        color: var(--text-primary);
    }

    .close-btn {
        background: none;
        border: none;
        cursor: pointer;
        color: var(--text-secondary);
        padding: 0.25rem;
        display: flex;
        align-items: center;
    }

    .close-btn:hover {
        color: var(--text-primary);
    }

    .help-body {
        padding: 1.5rem;
        overflow-y: auto;
        line-height: 1.6;
    }

    .help-body h3 {
        margin: 1.25rem 0 0.5rem;
        font-size: 1rem;
        font-weight: 600;
        color: var(--text-primary);
    }

    .help-body p,
    .help-body li {
        color: var(--text-secondary);
        font-size: 0.9375rem;
    }

    .help-body ol,
    .help-body ul {
        padding-left: 1.5rem;
        margin: 0.5rem 0;
    }

    .help-body li {
        margin-bottom: 0.25rem;
    }
</style>
