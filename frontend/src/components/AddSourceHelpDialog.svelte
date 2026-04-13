<script>
    import X from "@lucide/svelte/icons/x";

    let { isOpen = $bindable(false) } = $props();

    function close() { isOpen = false; }

    $effect(() => {
        if (isOpen) {
            const origOverflow = document.body.style.overflow;
            const origPosition = document.body.style.position;
            const origTop = document.body.style.top;
            const origWidth = document.body.style.width;
            const scrollY = window.scrollY;
            document.body.style.overflow = 'hidden';
            document.body.style.position = 'fixed';
            document.body.style.top = `-${scrollY}px`;
            document.body.style.width = '100%';
            return () => {
                document.body.style.overflow = origOverflow;
                document.body.style.position = origPosition;
                document.body.style.top = origTop;
                document.body.style.width = origWidth;
                window.scrollTo(0, scrollY);
            };
        }
    });
</script>

{#if isOpen}
    <div class="backdrop" onclick={close} role="presentation">
        <div
            class="dialog"
            role="dialog"
            aria-modal="true"
            aria-label="About Sources"
            tabindex="-1"
            onclick={(e) => e.stopPropagation()}
            onkeydown={(e) => { if (e.key === 'Escape') close(); }}
        >
            <div class="help-header">
                <h3>About Chapter Sources</h3>
                <button class="close-btn" onclick={close} aria-label="Close">
                    <X size="20"/>
                </button>
            </div>

            <div class="help-body">
                <p>
                    Sources provide reference data — chapter titles and/or timestamps — that Achew
                    can use when processing your audiobook. There are two kinds of sources:
                    Full chapter, and title-only.
                </p>

                <h4>Full chapter sources <span class="tag">timestamps + titles</span></h4>
                <p>
                    Full chapter sources contain both a timestamp and a title for each chapter.
                    They can be used to start the <em>Chapter Realignment</em>, <em>Regenerate Titles</em>,
                    and <em>Quick Edit</em> workflows, and can be used for cue comparison when selecting
                    initial chapters in the <em>Smart Detect</em> workflow. 
                </p>
                <p>They can also be used anywhere that title-only sources are used.</p>

                <p class="section-title">Supported sources:</p>
                <ul>
                    <li>
                        <strong>Audiobookshelf Chapters</strong> — ABS's existing chapter data for the
                        selected book. This source is automatically added if available.
                    </li>
                    <li>
                        <strong>Embedded Chapters</strong> — chapter info embedded in the audiobook files,
                        as provided by ABS. This source is automatically added if available.
                    </li>
                    <li>
                        <strong>File Data</strong> — chapter data inferred from the audiobook files, using
                        file names and durations. This source is automatically added for multi-file audiobooks.
                    </li>
                    <li>
                        <strong>Audnexus</strong> — chapter data obtained from Audnexus using an Amazon
                        Standard Identification Number (ASIN). This is the source Audiobookshelf itself uses
                        to fetch chapter data when the book has an associated ASIN. This source is
                        automatically added if an ASIN is assigned to the selected book in ABS. You may also search
                        for, preview chapters for, and add new Audnexus sources from the Add Chapter Source dialog.
                    </li>
                    <li>
                        <strong>JSON</strong> — a .json file containing an array of objects. These can be
                        uploaded through the Add Chapter Source dialog. Library Files* named <em>"chapters.json"</em> are
                        automatically detected and added. Achew attempts to automatically find timestamps** and
                        titles, but it helps to use predictable field names like <code>start</code> or
                        <code>timestamp</code> and <code>name</code> or <code>title</code>. Here is an example:
                        <pre><code>[
    {'{'}
        "timestamp": 0,
        "title": "Opening Credits"
    {'}'},
    {'{'}
        "timestamp": 18.453,
        "title": "Chapter 1: The Beginning"
    {'}'},
    ...etc...
]</code></pre>
                    </li>
                    <li>
                        <strong>CSV</strong> — a .csv file containing columns for both timestamps and titles.
                        These can be added through the Add Chapter Source dialog. Library Files* named <em>"chapters.csv"</em>
                        are automatically detected and added. Achew attempts to automatically find the timestamp**
                        and title columns, even without column names, but it helps to use predictable column names
                        like <code>start</code> or <code>timestamp</code> and <code>name</code> or <code>title</code>.
                    </li>
                    <li>
                        <strong>CUE Sheet</strong> — a standard .cue file. These can be uploaded through the Add Chapter Source
                        dialog. Any Library Files* with the <em>".cue"</em> extension are automatically detected and added.
                    </li>
                </ul>

                <h4>Title-only sources <span class="tag">titles only</span></h4>
                <p>
                    Title-only sources provide only chapter titles with no timestamps.
                    They can be used as a reference when cleaning up chapter titles with AI,
                    and when applying titles to chapters using the Apply Titles feature.
                    They cannot be used for chapter alignment.
                </p>
                <p class="section-title">Supported sources:</p>
                <ul>
                    <li>
                        <strong>Text File</strong> — a plain .txt file containing one title per line; blank lines are ignored.
                        These can be uploaded through the Add Chapter Source dialog. Library Files* named <em>"titles.txt"</em>
                        are automatically detected and added.
                    </li>
                    <li>
                        <strong>EPUB</strong> — an epub e-book file; chapter titles are extracted from its table of contents.
                        These can be uploaded through the Add Chapter Source dialog. Any Library Files* with the <em>".epub"</em>
                        extension are automatically detected and added.
                    </li>
                    <li>
                        <strong>Custom List</strong> — a user-defined list of chapter titles. An empty list is automatically
                        added, and can be edited directly in Achew.
                    </li>
                </ul>

                <hr />

                <p>
                    <span class="section-title">*Library Files</span> are files stored in the same directory as your audiobook file(s). These can be
                    viewed in the <em>Library Files</em> section of the book's detail page in Audiobookshelf.
                </p>

                <p><span class="section-title">**Timestamps</span> in JSON and CSV files can be in any of these formats:</p>
                <ul>
                    <li><code>H:MM:SS</code> or <code>H:MM:SS.ms</code> — e.g. <code>1:02:34</code> or <code>1:02:34.500</code></li>
                    <li><code>M:SS</code> or <code>M:SS.ms</code> — e.g. <code>62:34</code> or <code>62:34.500</code></li>
                    <li>A plain number in seconds — e.g. <code>3754</code> or <code>3754.5</code></li>
                    <li>A plain number in milliseconds — e.g. <code>3754000</code></li>
                </ul>
            </div>
        </div>
    </div>
{/if}

<style>
    .backdrop {
        position: fixed;
        inset: 0;
        background: rgba(0, 0, 0, 0.6);
        backdrop-filter: blur(2px);
        z-index: 1100;
        display: flex;
        align-items: center;
        justify-content: center;
        padding: 1rem;
    }

    .dialog {
        background: var(--bg-primary);
        border: 1px solid var(--border-color);
        border-radius: 12px;
        width: 100%;
        max-width: 720px;
        max-height: 88vh;
        display: flex;
        flex-direction: column;
        overflow: hidden;
    }

    .help-header {
        display: flex;
        align-items: center;
        justify-content: space-between;
        padding: 1.25rem 1.5rem;
        border-bottom: 1px solid var(--border-color);
        flex-shrink: 0;
    }

    .help-header h3 {
        margin: 0;
        font-size: 1.1rem;
        font-weight: 600;
        color: var(--text-primary);
    }

    .close-btn {
        background: none;
        border: none;
        cursor: pointer;
        color: var(--text-secondary);
        padding: 0.25rem;
        border-radius: 6px;
        display: flex;
        align-items: center;
        transition: background 0.15s;
    }

    .close-btn:hover { background: var(--bg-tertiary); color: var(--text-primary); }

    :global(code) {
        font-family: monospace;
        font-size: 0.85em;
        padding: 0.1em 0.35em;
        border-radius: 4px;
        background: var(--bg-tertiary);
        color: var(--text-primary);
    }

    :global(pre) {
        margin: 0.5rem 0 0.25rem;
        border-radius: 6px;
        background: var(--bg-tertiary);
        border: 1px solid var(--border-color);
        overflow-x: auto;
    }

    :global(pre code) {
        display: block;
        padding: 0.5rem 0.5rem;
        background: none;
        border-radius: 0;
        font-size: 0.6rem;
        line-height: 1.6;
        white-space: pre;
    }

    .help-body {
        padding: 1.5rem;
        overflow-y: auto;
        line-height: 1.6;
    }

    .help-body h4 {
        display: flex;
        align-items: center;
        gap: 0.5rem;
        margin: 1.25rem 0 0.4rem;
        font-size: 1.1rem;
        font-weight: 600;
        color: var(--text-primary);
    }

    .help-body h4:first-of-type { margin-top: 0.75rem; }

    .tag {
        font-size: 0.72rem;
        font-weight: 500;
        padding: 0.15rem 0.45rem;
        border-radius: 4px;
        background: var(--bg-tertiary);
        color: var(--text-secondary);
    }

    .help-body p {
        margin: 0 0 0.5rem;
        font-size: 0.9375rem;
        line-height: 1.5;
        color: var(--text-secondary);
    }

    .help-body .section-title {
        color: var(--text-primary);
        margin: 0.75rem 0 0.5rem;
    }

    .help-body ul {
        margin: 0.25rem 0 0.5rem;
        padding-left: 1.5rem;
    }

    .help-body li strong {
        color: var(--text-primary);
    }

    .help-body li {
        font-size: 0.9375rem;
        color: var(--text-secondary);
        margin-bottom: 0.5rem;
    }

    .help-body hr {
        border: none;
        border-top: 1px solid var(--border-color);
        margin: 2.5rem 0 1.5rem 0;
    }
</style>
