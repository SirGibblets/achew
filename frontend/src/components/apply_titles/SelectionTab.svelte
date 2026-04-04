<script>
    import {onMount, onDestroy, tick} from "svelte";
    import {chapters} from "../../stores/session.js";
    import {audio, currentSegmentId, isPlaying} from "../../stores/audio.js";
    import Pause from "@lucide/svelte/icons/pause";
    import Play from "@lucide/svelte/icons/play";

    let {
        source = null,
        mappings = $bindable([]),
    } = $props();

    let allChapters = $derived($chapters.filter(c => !c.deleted));
    let sourceCues = $derived(source?.cues ?? []);

    let leftChecked = $state({});
    let rightChecked = $state([]);
    let lastSourceId = $state(null);

    $effect(() => {
        const sourceId = source?.id ?? null;
        if (sourceId !== lastSourceId) {
            const lc = {};
            for (const ch of allChapters) {
                lc[ch.id] = ch.selected;
            }
            leftChecked = lc;
            rightChecked = sourceCues.map(() => true);
            lastSourceId = sourceId;
        }
    });

    let selectedChapters = $derived(
        allChapters.filter(ch => leftChecked[ch.id])
    );
    let selectedCues = $derived(
        sourceCues.filter((_, i) => rightChecked[i])
    );

    /* Pair Nth selected original with Nth selected source cue */
    let pairs = $derived(
        selectedChapters.slice(0, selectedCues.length).map((ch, i) => ({
            chapter: ch,
            cue: selectedCues[i],
        }))
    );

    /* Map from chapter id to its paired cue for quick lookup */
    let pairMap = $derived(new Map(pairs.map(p => [p.chapter.id, p.cue])));

    let lastClickedLeft = $state(null);
    let lastClickedRight = $state(null);

    function handleLeftCheck(chapterId, event) {
        const allIds = allChapters.map(ch => ch.id);
        const idx = allIds.indexOf(chapterId);
        const newValue = !leftChecked[chapterId];

        const next = { ...leftChecked };
        if (event.shiftKey && lastClickedLeft !== null && lastClickedLeft !== idx) {
            const lo = Math.min(lastClickedLeft, idx);
            const hi = Math.max(lastClickedLeft, idx);
            for (let i = lo; i <= hi; i++) {
                next[allIds[i]] = newValue;
            }
        } else {
            next[chapterId] = newValue;
        }
        leftChecked = next;

        lastClickedLeft = idx;
    }

    function handleRightCheck(cueIdx, event) {
        const newValue = !rightChecked[cueIdx];

        const next = [...rightChecked];
        if (event.shiftKey && lastClickedRight !== null && lastClickedRight !== cueIdx) {
            const lo = Math.min(lastClickedRight, cueIdx);
            const hi = Math.max(lastClickedRight, cueIdx);
            for (let i = lo; i <= hi; i++) {
                next[i] = newValue;
            }
        } else {
            next[cueIdx] = newValue;
        }
        rightChecked = next;

        lastClickedRight = cueIdx;
    }

    $effect(() => {
        mappings = pairs.map(p => ({
            chapter_id: p.chapter.id,
            new_title: p.cue.title,
        }));
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

    let leftColEl = $state(null);
    let rightColEl = $state(null);
    let svgEl = $state(null);

    let leftRowEls = $state({});
    let rightRowEls = $state({});

    let connectorPaths = $state([]);

    function computeConnectors() {
        if (!svgEl || !leftColEl || !rightColEl) return;

        const svgRect = svgEl.getBoundingClientRect();
        const paths = [];

        for (const p of pairs) {
            const leftEl = leftRowEls[p.chapter.id];
            const cueIdx = sourceCues.indexOf(p.cue);
            const rightEl = rightRowEls[cueIdx];
            if (!leftEl || !rightEl) continue;

            const lRect = leftEl.getBoundingClientRect();
            const rRect = rightEl.getBoundingClientRect();

            const y1 = lRect.top + lRect.height / 2 - svgRect.top;
            const y2 = rRect.top + rRect.height / 2 - svgRect.top;

            const arrowLength = 8;
            const arrowHalfWidth = 4;
            const x1 = arrowLength;
            const x2 = svgRect.width;
            const cx = svgRect.width / 2;

            const d = `M ${x1} ${y1} C ${cx} ${y1}, ${cx} ${y2}, ${x2} ${y2}`;
            const arrowPoints = `0,${y1} ${arrowLength},${y1 - arrowHalfWidth} ${arrowLength},${y1 + arrowHalfWidth}`;

            paths.push({ d, arrowPoints });
        }
        connectorPaths = paths;
    }

    $effect(() => {
        pairs;
        tick().then(() => requestAnimationFrame(computeConnectors));
    });

    let isSyncScrolling = false;

    /** Interpolation-based scroll sync */
    function syncOther(sourceEl, sourceRowEls, sourceKeyFn, targetEl, targetRowEls, targetKeyFn) {
        if (isSyncScrolling || !sourceEl || !targetEl || pairs.length === 0) return;
        isSyncScrolling = true;

        const scrollTop = sourceEl.scrollTop;
        const maxScroll = sourceEl.scrollHeight - sourceEl.clientHeight;

        /*
         * Build a mapping: for each pair, record the source scrollTop at which
         * that pair's row sits at the top of the viewport, and the corresponding
         * target scrollTop that would align the target pair row to the top.
         */
        const anchors = [];
        for (let i = 0; i < pairs.length; i++) {
            const srcEl = sourceRowEls[sourceKeyFn(i)];
            const tgtEl = targetRowEls[targetKeyFn(i)];
            if (!srcEl || !tgtEl) continue;
            anchors.push({
                srcOffset: srcEl.offsetTop,
                tgtOffset: tgtEl.offsetTop,
            });
        }

        if (anchors.length === 0) {
            isSyncScrolling = false;
            return;
        }

        let targetScrollTop;

        if (anchors.length === 1) {
            /* Single pair: offset by the difference */
            targetScrollTop = scrollTop - anchors[0].srcOffset + anchors[0].tgtOffset;
        } else {
            /*
             * Add synthetic anchors at scroll boundaries (0,0) and (max,max)
             * so interpolation covers the full range smoothly.
             */
            const targetMaxScroll = targetEl.scrollHeight - targetEl.clientHeight;
            const allAnchors = [
                { srcOffset: 0, tgtOffset: 0 },
                ...anchors,
                { srcOffset: maxScroll, tgtOffset: targetMaxScroll },
            ];

            /* Find the two anchors that bracket the current scrollTop */
            let lo = 0;
            for (let i = 1; i < allAnchors.length; i++) {
                if (allAnchors[i].srcOffset > scrollTop) break;
                lo = i;
            }
            const hi = Math.min(lo + 1, allAnchors.length - 1);

            if (lo === hi) {
                targetScrollTop = allAnchors[lo].tgtOffset;
            } else {
                /* Linearly interpolate between the two anchors */
                const range = allAnchors[hi].srcOffset - allAnchors[lo].srcOffset;
                const t = range > 0 ? (scrollTop - allAnchors[lo].srcOffset) / range : 0;
                targetScrollTop = allAnchors[lo].tgtOffset + t * (allAnchors[hi].tgtOffset - allAnchors[lo].tgtOffset);
            }
        }

        targetEl.scrollTop = Math.max(0, targetScrollTop);

        requestAnimationFrame(() => {
            isSyncScrolling = false;
            computeConnectors();
        });
    }

    function syncFromLeft() {
        syncOther(
            leftColEl, leftRowEls, i => pairs[i].chapter.id,
            rightColEl, rightRowEls, i => sourceCues.indexOf(pairs[i].cue)
        );
    }

    function syncFromRight() {
        syncOther(
            rightColEl, rightRowEls, i => sourceCues.indexOf(pairs[i].cue),
            leftColEl, leftRowEls, i => pairs[i].chapter.id
        );
    }

    /*
     * SVG connector column: forward wheel events to the column on the
     * cursor's side (left half → left column, right half → right column).
     */
    function handleSvgWheel(e) {
        if (!svgEl) return;
        e.preventDefault();
        const { left, width } = svgEl.getBoundingClientRect();
        const target = e.clientX < left + width / 2 ? leftColEl : rightColEl;
        if (target) target.scrollTop += e.deltaY;
    }

    onMount(() => {
        leftColEl?.addEventListener('scroll', syncFromLeft, { passive: true });
        rightColEl?.addEventListener('scroll', syncFromRight, { passive: true });
        svgEl?.addEventListener('wheel', handleSvgWheel, { passive: false });
    });

    onDestroy(() => {
        leftColEl?.removeEventListener('scroll', syncFromLeft);
        rightColEl?.removeEventListener('scroll', syncFromRight);
        svgEl?.removeEventListener('wheel', handleSvgWheel);
    });
</script>

<p class="tab-explanation">
    Titles are applied in order — each checked chapter on the left receives the title of the
    corresponding checked chapter on the right. Uncheck items on either side to adjust the pairing.
</p>

<div class="selection-layout">
    <!-- Left column: original chapters -->
    <div class="col col-left" bind:this={leftColEl}>
        {#each allChapters as chapter (chapter.id)}
            {@const paired = pairMap.get(chapter.id)}
            <!-- svelte-ignore a11y_click_events_have_key_events -->
            <!-- svelte-ignore a11y_no_noninteractive_element_interactions -->
            <label
                class="col-row"
                class:checked={leftChecked[chapter.id]}
                bind:this={leftRowEls[chapter.id]}
                onclick={(e) => { e.preventDefault(); handleLeftCheck(chapter.id, e); }}
            >
                <input type="checkbox" checked={leftChecked[chapter.id]} />
                <span class="ts">{formatTimestamp(chapter.timestamp)}</span>
                <button class="play-btn" onclick={(e) => { e.stopPropagation(); playChapter(chapter.id); }} title="Play">
                    {#if $currentSegmentId === chapter.id && $isPlaying}
                        <Pause size="14"/>
                    {:else}
                        <Play size="14"/>
                    {/if}
                </button>
                <span class="title">
                    {#if paired}
                        <span class="title-original-strikethrough" class:fallback={!chapter.current_title}>{chapter.current_title || "No Title"}</span>
                        <span class="title-new">{paired.title}</span>
                    {:else}
                        <span class="title-original" class:fallback={!chapter.current_title}>{chapter.current_title || "No Title"}</span>
                    {/if}
                </span>
            </label>
        {/each}
    </div>

    <!-- SVG connector overlay -->
    <svg
        class="connector-svg"
        bind:this={svgEl}
        aria-hidden="true"
    >
        {#each connectorPaths as path}
            <path d={path.d} class="connector-line" />
            <polygon points={path.arrowPoints} class="connector-arrow" />
        {/each}
    </svg>

    <!-- Right column: source cues -->
    <div class="col col-right" bind:this={rightColEl}>
        {#each sourceCues as cue, i (i)}
            <!-- svelte-ignore a11y_click_events_have_key_events -->
            <!-- svelte-ignore a11y_no_noninteractive_element_interactions -->
            <label
                class="col-row"
                class:checked={rightChecked[i]}
                bind:this={rightRowEls[i]}
                onclick={(e) => { e.preventDefault(); handleRightCheck(i, e); }}
            >
                <input type="checkbox" checked={rightChecked[i]} />
                <span class="title">
                    <span class="title-original">{cue.title}</span>
                </span>
            </label>
        {/each}
    </div>
</div>

<style>
    .tab-explanation {
        color: var(--text-muted);
        font-size: 0.85rem;
        margin: 0 0 0.75rem 0;
        line-height: 1.4;
        text-align: center;
    }

    .selection-layout {
        display: grid;
        grid-template-columns: 12fr 42px 9fr;
        position: relative;
        height: 360px;
        overflow: hidden;
        border: 1px solid var(--border-color);
        border-radius: 8px;
    }

    .col {
        overflow-y: auto;
        height: 100%;
        scrollbar-width: none;
    }

    .col-left {
        margin-right: -16px;
    }

    .col-right {
        margin-left: -12px;
    }

    .col::-webkit-scrollbar {
        display: none;
    }

    .col-row {
        display: flex;
        align-items: center;
        gap: 0.4rem;
        padding: 0.35rem 0.6rem;
        min-height: 3rem;
        font-size: 0.82rem;
        cursor: pointer;
        opacity: 0.4;
        user-select: none;
        transition: opacity 0.15s;
    }

    .col-row:nth-child(even) {
        background: var(--hover-bg, rgba(128, 128, 128, 0.06));
    }

    .col-row:hover {
        opacity: 0.7;
    }

    .col-row.checked {
        opacity: 1;
    }

    .col-row input[type="checkbox"] {
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

    .ts {
        flex-shrink: 0;
        font-family: monospace;
        font-size: 0.72rem;
        color: var(--text-muted);
        min-width: 3.5rem;
    }

    .title {
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

    .connector-svg {
        width: 100%;
        height: 100%;
        pointer-events: all;
        overflow: visible;
    }

    .connector-line {
        fill: none;
        stroke: var(--text-muted);
        stroke-width: 1.5;
        opacity: 0.6;
    }

    .connector-arrow {
        fill: var(--text-muted);
        opacity: 0.6;
    }
</style>
