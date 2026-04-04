<script>
    import {chapters} from "../../stores/session.js";
    import {audio, currentSegmentId, isPlaying} from "../../stores/audio.js";
    import Pause from "@lucide/svelte/icons/pause";
    import Play from "@lucide/svelte/icons/play";

    let {
        source = null,
        mappings = $bindable([]),
    } = $props();

    async function playChapter(chapterId) {
        try {
            if ($currentSegmentId === chapterId && $isPlaying) {
                audio.stop();
            } else {
                const chapter = allChapters.find(ch => ch.id === chapterId);
                if (chapter) await audio.play(chapterId, chapter.timestamp);
            }
        } catch (err) {
            // silently ignore
        }
    }

    /*
     * Alignment tolerance in seconds
     */
    const TOLERANCE = 5;

    let allChapters = $derived($chapters.filter(c => !c.deleted));

    /**
     * For each original chapter, find the closest source cue within TOLERANCE.
     * Deduplicates: if two source cues match the same chapter, the closest wins.
     * Returns Map<chapter_id, { sourceTitle, chapter }>.
     */
    let alignedMap = $derived.by(() => {
        if (!source?.cues?.length) return new Map();

        const map = new Map();
        for (const cue of source.cues) {
            let best = null;
            let bestDist = Infinity;
            for (const ch of allChapters) {
                const d = Math.abs(cue.timestamp - ch.timestamp);
                if (d <= TOLERANCE && d < bestDist) {
                    bestDist = d;
                    best = ch;
                }
            }
            if (!best) continue;

            const existing = map.get(best.id);
            if (!existing || bestDist < existing.dist) {
                map.set(best.id, { sourceTitle: cue.title, chapter: best, dist: bestDist });
            }
        }
        return map;
    });

    let alignedCount = $derived(alignedMap.size);

    let checked = $state({});
    let lastSourceId = $state(null);

    let lastClickedIdx = $state(null);

    let alignedIds = $derived(
        allChapters.map(ch => ch.id).filter(id => alignedMap.has(id))
    );

    function handleCheck(chapterId, event) {
        const idx = alignedIds.indexOf(chapterId);
        const newValue = !checked[chapterId];

        const next = { ...checked };
        if (event.shiftKey && lastClickedIdx !== null && lastClickedIdx !== idx) {
            const lo = Math.min(lastClickedIdx, idx);
            const hi = Math.max(lastClickedIdx, idx);
            for (let i = lo; i <= hi; i++) {
                next[alignedIds[i]] = newValue;
            }
        } else {
            next[chapterId] = newValue;
        }
        checked = next;

        lastClickedIdx = idx;
    }

    $effect(() => {
        const sourceId = source?.id ?? null;
        const pairs = alignedMap;
        if (sourceId !== lastSourceId || Object.keys(checked).length === 0) {
            const next = {};
            for (const [id] of pairs) {
                next[id] = true;
            }
            checked = next;
            lastSourceId = sourceId;
        }
    });

    $effect(() => {
        const result = [];
        for (const [chapterId, pair] of alignedMap) {
            if (checked[chapterId]) {
                result.push({
                    chapter_id: chapterId,
                    new_title: pair.sourceTitle,
                });
            }
        }
        mappings = result;
    });

    function formatTimestamp(seconds) {
        const hours = Math.floor(seconds / 3600);
        const minutes = Math.floor((seconds % 3600) / 60);
        const secs = Math.floor(seconds % 60);

        if (hours > 0) {
            return `${hours}:${minutes.toString().padStart(2, "0")}:${secs.toString().padStart(2, "0")}`;
        }
        return `${minutes}:${secs.toString().padStart(2, "0")}`;
    }
</script>

<p class="tab-explanation">
    {#if alignedCount === 0}
        No chapters with matching timestamps were found in the selected source.
    {:else}
        {alignedCount} of {allChapters.length} chapters have a matching (timestamp-aligned) chapter in the
        selected source.<br/>Uncheck any titles don't want to apply.
    {/if}
</p>

<div class="chapter-list">
    {#each allChapters as chapter (chapter.id)}
        {@const pair = alignedMap.get(chapter.id)}
        {#if pair}
            <!-- svelte-ignore a11y_click_events_have_key_events -->
            <!-- svelte-ignore a11y_no_noninteractive_element_interactions -->
            <label class="row aligned" class:checked={checked[chapter.id]}
                   onclick={(e) => { e.preventDefault(); handleCheck(chapter.id, e); }}>
                <input type="checkbox" checked={checked[chapter.id]} />
                <span class="chapter-ts">{formatTimestamp(chapter.timestamp)}</span>
                <button class="play-btn" onclick={(e) => { e.stopPropagation(); playChapter(chapter.id); }} title="Play">
                    {#if $currentSegmentId === chapter.id && $isPlaying}
                        <Pause size="14"/>
                    {:else}
                        <Play size="14"/>
                    {/if}
                </button>
                <span class="chapter-title">
                    {#if checked[chapter.id]}
                        <span class="title-original-strikethrough" class:fallback={!chapter.current_title}>{chapter.current_title || "No Title"}</span>
                        <span class="title-new">{pair.sourceTitle}</span>
                    {:else}
                        <span class="title-original" class:fallback={!chapter.current_title}>{chapter.current_title || "No Title"}</span>
                    {/if}
                </span>
            </label>
        {:else}
            <div class="row unaligned">
                <span class="chapter-ts">{formatTimestamp(chapter.timestamp)}</span>
                <button class="play-btn" onclick={() => playChapter(chapter.id)} title="Play">
                    {#if $currentSegmentId === chapter.id && $isPlaying}
                        <Pause size="14"/>
                    {:else}
                        <Play size="14"/>
                    {/if}
                </button>
                <span class="chapter-title">
                    <span class="title-original" class:fallback={!chapter.current_title}>{chapter.current_title || "No Title"}</span>
                </span>
            </div>
        {/if}
    {/each}
</div>

<style>
    .tab-explanation {
        color: var(--text-muted);
        font-size: 0.85rem;
        margin: 0 0 0.75rem 0;
        line-height: 1.4;
        text-align: center;
    }

    .chapter-list {
        overflow-y: auto;
        max-height: 360px;
        border: 1px solid var(--border-color);
        border-radius: 8px;
    }

    .row {
        display: flex;
        align-items: center;
        gap: 0.4rem;
        padding: 0.35rem 0.6rem;
        min-height: 3rem;
        font-size: 0.82rem;
    }

    .row:nth-child(even) {
        background: var(--hover-bg, rgba(128, 128, 128, 0.06));
    }

    .row.unaligned {
        opacity: 0.4;
    }

    .row.aligned {
        opacity: 0.5;
        cursor: pointer;
        transition: opacity 0.15s;
    }

    .row.aligned:hover {
        opacity: 0.7;
    }

    .row.aligned.checked {
        opacity: 1;
    }

    .row {
        user-select: none;
    }

    .row input[type="checkbox"] {
        flex-shrink: 0;
        cursor: pointer;
        pointer-events: none;
    }

    .play-btn {
        flex-shrink: 0;
        width: 1.4rem;
        height: 1.4rem;
        border-radius: 50%;
        border: none;
        background: transparent;
        color: var(--text-muted);
        cursor: pointer;
        display: flex;
        align-items: center;
        justify-content: center;
        padding: 0;
        transition: color 0.15s, background 0.15s;
    }

    .play-btn:hover {
        color: var(--primary-color);
        background: var(--hover-bg);
    }

    .chapter-ts {
        flex-shrink: 0;
        font-family: monospace;
        font-size: 0.72rem;
        color: var(--text-muted);
        min-width: 3.5rem;
    }

    .chapter-title {
        flex: 1;
        min-width: 0;
        display: flex;
        flex-direction: column;
        justify-content: center;
    }

    .title-new {
        color: var(--primary-color);
        font-weight: 500;
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
    }

    .title-original {
        color: var(--text-secondary);
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
    }

    .title-original-strikethrough {
        color: var(--text-muted);
        text-decoration: line-through;
        font-size: 0.65rem;
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
        line-height: 1.1;
    }

    .fallback {
        font-style: italic;
    }
</style>
