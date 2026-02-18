<script>
    import {onMount} from "svelte";
    import {session} from "../stores/session.js";
    import {api} from "../utils/api.js";

    // Icons
    import BookDashed from "@lucide/svelte/icons/book-dashed";
    import ChevronDown from "@lucide/svelte/icons/chevron-down";
    import CircleQuestionMark from "@lucide/svelte/icons/circle-question-mark";
    import Clock4 from "@lucide/svelte/icons/clock-4";

    const NUM_BARS = 100;
    const SENSITIVITY_FADE_DURATION = 2400; // 40 minutes in seconds
    const MAX_CUES = 500;

    let loading = false;
    let allCues = [];  // [{timestamp, gap}] — capped at MAX_CUES by longest gap
    let cuesCapped = false; // true if original cue list exceeded MAX_CUES
    let bookDuration = 0;
    let error = null;
    let sliderValue = 0.5; // 0–1, logarithmically mapped to threshold
    let sensitivity = 0;   // -2 to 2, adjustment for edge cues
    let showSensitivity = false;
    let existingCueSources = [];
    let activeComparisonSource = null;
    let showUsageHints = false;
    let includeUnalignedSources = {};
    let showTooltip = false;
    let showSensitivityTooltip = false;

    let timelineTooltip = {
        show: false,
        showTop: false,
        showBottom: false,
        x: 0,
        topContent: '',
        bottomContent: ''
    };

    $: innerWidth = 0;

    let isDarkMode = false;

    function updateThemeStatus() {
        if (typeof document !== "undefined") {
            isDarkMode = document.documentElement.getAttribute("data-theme") === "dark";
        }
    }

    onMount(() => {
        updateThemeStatus();
        const observer = new MutationObserver((mutations) => {
            mutations.forEach((mutation) => {
                if (mutation.type === "attributes" && mutation.attributeName === "data-theme") {
                    updateThemeStatus();
                }
            });
        });
        if (typeof document !== "undefined") {
            observer.observe(document.documentElement, {
                attributes: true,
                attributeFilter: ["data-theme"],
            });
        }
        return () => observer.disconnect();
    });

    onMount(async () => {
        await loadCueSets();
    });

    $: isComparing = activeComparisonSource !== null;

    // Largest and smallest gaps among all detected cues
    $: maxGap = allCues.length > 0 ? Math.max(...allCues.map(c => c.gap)) : 10;
    $: minGap = allCues.length > 0 ? Math.min(...allCues.map(c => c.gap)) : 1.0;

    // Logarithmic interpolation:
    //   slider=0 → threshold=maxGap (fewest chapters)
    //   slider=1 → threshold=minGap (most chapters)
    function sliderToThreshold(s) {
        if (maxGap <= minGap) return minGap;
        return Math.exp(Math.log(maxGap) * (1 - s) + Math.log(minGap) * s);
    }

    // Inlined from sliderToThreshold so Svelte tracks maxGap, minGap, and sliderValue
    // directly as reactive dependencies. Calling the function hides them from Svelte's
    // static analysis, causing threshold to go stale when maxGap/minGap update on load.
    $: threshold = maxGap <= minGap
        ? minGap
        : Math.exp(Math.log(maxGap) * (1 - sliderValue) + Math.log(minGap) * sliderValue);
    $: thresholdDisplay = threshold < 10 ? threshold.toFixed(1) + 's' : Math.round(threshold) + 's';
    // Inline effectiveGap here so Svelte tracks sensitivity and bookDuration as reactive deps.
    $: selectedCues = allCues.filter(c => {
        const nearStart = Math.max(0, 1 - c.timestamp / SENSITIVITY_FADE_DURATION);
        const nearEnd = Math.max(0, 1 - (bookDuration - c.timestamp) / SENSITIVITY_FADE_DURATION);
        return (c.gap + sensitivity * Math.max(nearStart, nearEnd)) >= threshold;
    });
    // Always include 0 as the first timestamp (start of book), matching original behavior.
    $: selectedTimestamps = [0, ...selectedCues.map(c => c.timestamp)];

    // Bar chart: bar i represents the gap range
    //   [sliderToThreshold((i+1)/100), sliderToThreshold(i/100))
    // Bars to the left of the current slider position are "selected" (white).
    $: barData = (() => {
        if (allCues.length === 0 || maxGap <= minGap) return Array(NUM_BARS).fill(0);
        const counts = Array(NUM_BARS).fill(0);
        for (let i = 0; i < NUM_BARS; i++) {
            const gapLow = sliderToThreshold((i + 1) / NUM_BARS);
            const gapHigh = sliderToThreshold(i / NUM_BARS);
            counts[i] = allCues.filter(c => c.gap >= gapLow && c.gap < gapHigh).length;
        }
        return counts;
    })();
    $: maxBarCount = Math.max(1, ...barData);

    async function loadCueSets() {
        if ($session.step !== "cue_set_selection") return;
        loading = true;
        error = null;
        try {
            const response = await api.session.getCueSets();
            const rawCues = response.detected_cues || [];
            // Keep only the MAX_CUES cues with the largest gaps; sort back by timestamp.
            cuesCapped = rawCues.length > MAX_CUES;
            allCues = (cuesCapped
                ? [...rawCues].sort((a, b) => b.gap - a.gap).slice(0, MAX_CUES)
                : rawCues
            ).sort((a, b) => a.timestamp - b.timestamp);
            bookDuration = response.book_duration;
            existingCueSources = response.existing_cue_sources || [];

            includeUnalignedSources = {};
            existingCueSources.forEach((source) => {
                includeUnalignedSources[source.id] = false;
            });

            // Pre-select a threshold that produces approximately the same number of
            // chapters as the highest chapter count among existing cue sources.
            let highestExistingCount = 0;
            existingCueSources.forEach((source) => {
                if (source.cues && source.cues.length > 0) {
                    highestExistingCount = Math.max(highestExistingCount, source.cues.length);
                }
            });

            if (highestExistingCount > 0 && allCues.length > 0) {
                // Compute maxGap/minGap locally — the reactive $: declarations won't
                // have updated yet at this point in the async function.
                const localMaxGap = Math.max(...allCues.map(c => c.gap));
                const localMinGap = Math.min(...allCues.map(c => c.gap));
                const sorted = [...allCues].sort((a, b) => b.gap - a.gap);
                // source.cues includes t=0 as its first entry, same as selectedTimestamps.
                // To match N total timestamps we need N-1 detected cues, so the threshold
                // should be the (N-1)th largest gap → index N-2.
                const targetIndex = Math.min(Math.max(0, highestExistingCount - 2), sorted.length - 1);
                const targetGap = sorted[targetIndex].gap;
                let raw = 0.5;
                if (localMaxGap > localMinGap) {
                    const clamped = Math.max(localMinGap, Math.min(localMaxGap, targetGap));
                    raw = Math.log(localMaxGap / clamped) / Math.log(localMaxGap / localMinGap);
                }
                sliderValue = Math.ceil(Math.min(1, Math.max(0, raw)) * 100) / 100;
            } else {
                sliderValue = 0.5;
            }
        } catch (err) {
            error = `Failed to load cues: ${err.message}`;
            console.error("Error loading cues:", err);
        } finally {
            loading = false;
        }
    }

    async function proceedWithSelection() {
        if (selectedTimestamps.length === 0) {
            alert("No chapters selected. Adjust the slider to include at least one chapter.");
            return;
        }
        loading = true;
        error = null;
        try {
            const unalignedOptions = [];
            Object.keys(includeUnalignedSources).forEach((sourceId) => {
                if (includeUnalignedSources[sourceId]) {
                    unalignedOptions.push(sourceId);
                }
            });
            await api.session.selectCueSet(selectedTimestamps, unalignedOptions);
        } catch (err) {
            error = `Failed to select chapters: ${err.message}`;
            console.error("Error selecting chapters:", err);
        } finally {
            loading = false;
        }
    }

    function formatTimelineTime(seconds) {
        const hours = Math.floor(seconds / 3600);
        const minutes = Math.floor((seconds % 3600) / 60);
        const secs = Math.floor(seconds % 60);
        if (hours > 0) {
            return `${hours}:${minutes.toString().padStart(2, "0")}:${secs.toString().padStart(2, "0")}`;
        }
        return `${minutes}:${secs.toString().padStart(2, "0")}`;
    }

    function toggleCueSourceDisplay(sourceId) {
        activeComparisonSource = activeComparisonSource === sourceId ? null : sourceId;
    }

    function isChapterAligned(existingTimestamp, selectedTs, tolerance = 5) {
        return selectedTs.some((ts) => Math.abs(existingTimestamp - ts) <= tolerance);
    }

    function calculateAlignmentPercentage(existingTimestamps, selectedTs) {
        if (!existingTimestamps || !selectedTs || existingTimestamps.length === 0) return 0;
        const alignedCount = existingTimestamps.filter((ts) =>
            isChapterAligned(ts, selectedTs)
        ).length;
        return Math.round((alignedCount / existingTimestamps.length) * 100);
    }

    function getAlignmentColor(percentage) {
        if (percentage <= 50) return "var(--danger)";
        if (percentage <= 75) {
            const t = (percentage - 50) / 25;
            if (CSS.supports("color", "color-mix(in srgb, red 50%, blue 50%)")) {
                return `color-mix(in srgb, var(--danger) ${Math.round((1 - t) * 100)}%, var(--warning) ${Math.round(t * 100)}%)`;
            }
            return "var(--warning)";
        }
        const t = Math.min((percentage - 75) / 25, 1);
        if (CSS.supports("color", "color-mix(in srgb, red 50%, blue 50%)")) {
            return `color-mix(in srgb, var(--warning) ${Math.round((1 - t) * 100)}%, var(--primary-contrast) ${Math.round(t * 100)}%)`;
        }
        return "var(--primary-contrast)";
    }

    $: additionalTimestampCount = (() => {
        let count = 0;
        const tolerance = 5.0;
        existingCueSources.forEach((source) => {
            if (includeUnalignedSources[source.id]) {
                count += source.cues.filter(
                    (cue) => !selectedTimestamps.some((s) => Math.abs(cue.timestamp - s) <= tolerance)
                ).length;
            }
        });
        return count;
    })();

    $: hasAdditionalTimestamps = Object.values(includeUnalignedSources).some(v => v === true);
    $: totalChapterCount = selectedTimestamps.length + additionalTimestampCount;

    function handleTimelineMouseMove(event) {
        if (!selectedTimestamps || selectedTimestamps.length === 0) return;

        const timelineTrack = event.currentTarget;
        const rect = timelineTrack.getBoundingClientRect();
        const mouseX = event.clientX - rect.left;
        const timelineWidth = rect.width;
        const mousePercent = (mouseX / timelineWidth) * 100;

        let nearestTick = null;
        let nearestDistance = Infinity;

        selectedTimestamps.forEach((timestamp, index) => {
            if (index === 0) return;
            const tickPercent = (timestamp / bookDuration) * 100;
            const distance = Math.abs(mousePercent - tickPercent);
            if (distance < nearestDistance) {
                nearestDistance = distance;
                nearestTick = { type: 'new', timestamp, index, percent: tickPercent };
            }
        });

        if (activeComparisonSource) {
            const activeSource = existingCueSources.find((s) => s.id === activeComparisonSource);
            if (activeSource && activeSource.cues) {
                activeSource.cues.slice(1).forEach((cue, index) => {
                    const tickPercent = (cue.timestamp / bookDuration) * 100;
                    const distance = Math.abs(mousePercent - tickPercent);
                    if (distance < nearestDistance) {
                        nearestDistance = distance;
                        nearestTick = {
                            type: 'existing',
                            timestamp: cue.timestamp,
                            index: index + 1,
                            percent: tickPercent,
                            source: activeSource
                        };
                    }
                });
            }
        }

        if (nearestTick && nearestDistance < 5) {
            timelineTooltip.show = true;
            timelineTooltip.x = (nearestTick.percent / 100) * timelineWidth;

            if (isComparing) {
                if (nearestTick.type === 'existing') {
                    timelineTooltip.topContent = nearestTick.source.id === 'file_starts'
                        ? `File Start: ${formatTimelineTime(nearestTick.timestamp)}`
                        : `${nearestTick.source.short_name} Chapter: ${formatTimelineTime(nearestTick.timestamp)}`;
                    timelineTooltip.showTop = true;
                    const alignedNew = selectedTimestamps.find(ts => Math.abs(ts - nearestTick.timestamp) <= 5);
                    timelineTooltip.showBottom = !!alignedNew;
                    timelineTooltip.bottomContent = alignedNew ? formatTimelineTime(alignedNew) : '';
                } else {
                    timelineTooltip.bottomContent = formatTimelineTime(nearestTick.timestamp);
                    timelineTooltip.showBottom = true;
                    const activeSource = existingCueSources.find((s) => s.id === activeComparisonSource);
                    if (activeSource) {
                        const alignedExisting = activeSource.cues.find(cue =>
                            Math.abs(cue.timestamp - nearestTick.timestamp) <= 5
                        );
                        if (alignedExisting) {
                            timelineTooltip.topContent = activeSource.id === 'file_starts'
                                ? `File Start: ${formatTimelineTime(alignedExisting.timestamp)}`
                                : `${activeSource.short_name} Chapter: ${formatTimelineTime(alignedExisting.timestamp)}`;
                            timelineTooltip.showTop = true;
                        } else {
                            timelineTooltip.showTop = false;
                        }
                    } else {
                        timelineTooltip.showTop = false;
                    }
                }
            } else {
                timelineTooltip.showTop = true;
                timelineTooltip.showBottom = false;
                timelineTooltip.topContent = formatTimelineTime(nearestTick.timestamp);
            }
        } else {
            timelineTooltip.show = false;
        }
    }

    function handleTimelineMouseLeave() {
        timelineTooltip.show = false;
        timelineTooltip.showTop = false;
        timelineTooltip.showBottom = false;
    }
</script>

<svelte:window bind:innerWidth/>

<div class="chapter-selection">
    {#if error}
        <div class="alert alert-danger">
            {error}
            <button
                type="button"
                class="btn btn-sm btn-outline float-right"
                on:click={() => (error = null)}
            >
                Dismiss
            </button>
        </div>
    {/if}

    <div class="header">
        <h2>Select Initial Chapters</h2>
        <p>
            We've detected <strong>{cuesCapped ? `${MAX_CUES}+` : allCues.length}</strong> potential chapter cues.
            Use the slider below to select how many chapters to start with.
        </p>

        <!-- Usage Hints Section -->
        <div class="usage-hints-section">
            <button
                class="usage-hints-toggle"
                on:click={() => (showUsageHints = !showUsageHints)}
                aria-expanded={showUsageHints}
            >
                Usage Tips
                <div class="chevron {showUsageHints ? 'rotated' : ''}">
                    <ChevronDown size="12"/>
                </div>
            </button>

            {#if showUsageHints}
                <div class="usage-hints-content">
                    <ul class="hints-list">
                        <li>
                            <strong>Chapter Selection Slider:</strong> The bar chart behind the slider shows
                            the distribution of the 'gaps' of silence preceding the detected cues. Cues on
                            the left have the longest gaps and are more likely to represent real chapters,
                            whereas cues on the right have shorter gaps and are more likely to be false
                            positives.
                            <p>Moving the slider to the left will select fewer chapters, and moving it to
                            the right will select more chapters. Find a balance that feels right for this
                            book — there's no one-size-fits-all setting.</p>
                        </li>   
                        <li>
                            <strong>Timeline:</strong> Use the timeline to visualize how the selected
                            chapters are distributed throughout the audiobook. You'll typically want to
                            aim for a reasonably even distribution across the book's length.
                        </li>
                        <li>
                            <strong>Alignment:</strong> If existing chapter information is available from
                            an accurate source (embedded/Audnexus/etc.), compare against it and aim for
                            a high alignment percentage.
                        </li>
                        <li>
                            <strong>Intro/Outro:</strong> If you prefer to include various intro/outro
                            chapters (prologue/epilogue/dedication/etc.), a higher <em>Intro/Outro
                            Sensitivity</em> can help select more cues near the start and end of the book
                            that might otherwise be missed. Conversely, a lower value can help
                            exclude such chapters for those who prefer to focus on the main content.
                        </li>
                        <li>
                            <strong>Don't Sweat It:</strong> You can add and remove chapters in a later step.
                            Just aim for a reasonable starting point — bump the count up a little for good
                            measure and refine it later.
                        </li>
                    </ul>
                </div>
            {/if}
        </div>
    </div>

    {#if loading && allCues.length === 0}
        <div class="text-center p-4">
            <div class="spinner"></div>
            <p class="mt-2">Loading detected cues...</p>
        </div>
    {:else if allCues.length === 0}
        <div class="empty-state">
            <div class="empty-icon">
                <BookDashed size="48"/>
            </div>
            <h3>No cues available</h3>
            <p>Unable to find any chapter cues from the audio analysis.</p>
        </div>
    {:else}
        <!-- Timeline Visualization -->
        <div class="timeline-visualization">
            <div class="timeline-header">
                <h4>
                    <Clock4 size="16" style="margin-right: 0.5rem;"/>
                    Audiobook Timeline
                </h4>
                <div class="existing-chapter-toggles">
                    {#if existingCueSources.length > 0}
                        <div class="compare-label">
                            Compare to:
                            <div
                                class="tooltip-container"
                                role="button"
                                tabindex="0"
                                on:mouseenter={() => (showTooltip = true)}
                                on:mouseleave={() => (showTooltip = false)}
                                on:focus={() => (showTooltip = true)}
                                on:blur={() => (showTooltip = false)}
                                aria-label="Show timeline legend"
                            >
                                <CircleQuestionMark size="14"/>
                                {#if showTooltip}
                                    <div class="tooltip">
                                        <div class="tooltip-header">
                                            Timeline Comparison Legend
                                        </div>
                                        <div class="tooltip-content">
                                            <div class="legend-item">
                                                <div class="legend-visual">
                                                    <div class="mini-timeline">
                                                        <div class="mini-timeline-line"></div>
                                                        <div class="mini-timeline-line bottom"></div>
                                                        <div class="mini-tick existing unaligned" style="left: 50%"></div>
                                                    </div>
                                                </div>
                                                <div class="legend-text">
                                                    <strong>Red ticks:</strong> Unaligned existing cue
                                                </div>
                                            </div>

                                            <div class="legend-item">
                                                <div class="legend-visual">
                                                    <div class="mini-timeline">
                                                        <div class="mini-timeline-line"></div>
                                                        <div class="mini-timeline-line bottom"></div>
                                                        <div class="mini-tick new unaligned" style="left: 50%"></div>
                                                    </div>
                                                </div>
                                                <div class="legend-text">
                                                    {#if isDarkMode}
                                                        <strong>White ticks:</strong> Unaligned new cue
                                                    {:else}
                                                        <strong>Black ticks:</strong> Unaligned new cue
                                                    {/if}
                                                </div>
                                            </div>

                                            <div class="legend-item">
                                                <div class="legend-visual">
                                                    <div class="mini-timeline">
                                                        <div class="mini-timeline-line"></div>
                                                        <div class="mini-timeline-line bottom"></div>
                                                        <div class="mini-tick existing aligned" style="left: 50%"></div>
                                                        <div class="mini-tick new aligned" style="left: 50%"></div>
                                                    </div>
                                                </div>
                                                <div class="legend-text">
                                                    {#if isDarkMode}
                                                        <strong>Yellow/Green ticks:</strong> Aligned cues (both sources match)
                                                    {:else}
                                                        <strong>Blue/Purple ticks:</strong> Aligned cues (both sources match)
                                                    {/if}
                                                </div>
                                            </div>
                                        </div>
                                    </div>
                                {/if}
                            </div>
                        </div>
                    {/if}
                    {#each existingCueSources as source}
                        <button
                            class="toggle-btn"
                            class:active={activeComparisonSource === source.id}
                            on:click={() => toggleCueSourceDisplay(source.id)}
                            title="Show/hide {source.name} ({source.cues.length} chapters)"
                        >
                            {source.short_name} ({source.cues.length})
                        </button>
                    {/each}
                </div>
            </div>
            <div class="timeline-container">
                <div
                    class="timeline-track"
                    role="region"
                    aria-label="Timeline visualization with hover tooltips"
                    on:mousemove={handleTimelineMouseMove}
                    on:mouseleave={handleTimelineMouseLeave}
                >
                    {#if isComparing}
                        <div class="existing-timeline-line"></div>
                    {/if}
                    <div class="timeline-line {isComparing ? 'compared' : ''}"></div>

                    <!-- Existing chapters ticks for active comparison source -->
                    {#if activeComparisonSource}
                        {@const activeSource = existingCueSources.find((s) => s.id === activeComparisonSource)}
                        {#if activeSource && activeSource.cues}
                            {#each activeSource.cues.slice(1) as cue}
                                <div
                                    class="existing-timeline-tick {isChapterAligned(cue.timestamp, selectedTimestamps) ? 'aligned' : ''}"
                                    style="left: {(cue.timestamp / bookDuration) * 100}%"
                                ></div>
                            {/each}
                        {/if}
                    {/if}

                    <!-- Selected chapter ticks -->
                    <div class="timeline-ticks">
                        {#each selectedTimestamps as timestamp}
                            {@const activeSource = activeComparisonSource
                                ? existingCueSources.find((s) => s.id === activeComparisonSource)
                                : null}
                            {@const existingTs = activeSource ? activeSource.cues.map(c => c.timestamp) : []}
                            <div
                                class="timeline-tick {isComparing ? 'compared' : ''} {isChapterAligned(timestamp, existingTs) ? 'aligned' : ''}"
                                style="left: {(timestamp / bookDuration) * 100}%"
                            ></div>
                        {/each}
                    </div>

                    {#if timelineTooltip.show}
                        {#if timelineTooltip.showTop}
                            <div
                                class="timeline-tooltip timeline-tooltip-top"
                                style="left: {timelineTooltip.x}px"
                            >
                                {timelineTooltip.topContent}
                            </div>
                        {/if}
                        {#if timelineTooltip.showBottom}
                            <div
                                class="timeline-tooltip timeline-tooltip-bottom"
                                style="left: {timelineTooltip.x}px"
                            >
                                {timelineTooltip.bottomContent}
                            </div>
                        {/if}
                    {/if}
                </div>

                <div class="timeline-labels">
                    <span class="timeline-start">0:00</span>

                    {#if activeComparisonSource}
                        {@const activeSource = existingCueSources.find((s) => s.id === activeComparisonSource)}
                        {#if activeSource && activeSource.cues}
                            {@const existingTs = activeSource.cues.map(c => c.timestamp)}
                            {@const alignmentPct = calculateAlignmentPercentage(existingTs, selectedTimestamps)}
                            <span class="alignment-text" style="color: {getAlignmentColor(alignmentPct)}">
                                {#if innerWidth > 480}
                                    Alignment with {activeSource.name}: {alignmentPct}%
                                {:else}
                                    Alignment: {alignmentPct}%
                                {/if}
                            </span>
                        {/if}
                    {/if}

                    <span class="timeline-end">{formatTimelineTime(bookDuration)}</span>
                </div>
            </div>
        </div>

        <!-- Threshold Slider -->
        <div class="threshold-section">
            <div class="slider-bubble-area">
                <div class="selected-bubble" style="left: {0.5 + sliderValue * 99}%">
                    <div class="bubble-content">
                        <div class="bubble-main">
                            <span class="bubble-number">{selectedTimestamps.length}</span>
                            <span class="bubble-cues-label">chapters</span>
                        </div>
                    </div>
                    <div class="bubble-tail"></div>
                </div>
                <div class="bar-chart-wrapper" style:background={isDarkMode ? 'linear-gradient(to top, rgba(0,0,0,0.2), transparent)' : 'linear-gradient(to top, rgba(0,0,0,0.03), transparent)'}>
                <div class="bar-chart-svg-container" aria-hidden="true">
                    <svg class="bar-chart-svg" viewBox="0 0 100 32" preserveAspectRatio="none">
                        {#each barData as count, i}
                            {@const maxH = 30}
                            {@const minH = 5}
                            {@const h = count === 0 ? 0
                                : maxBarCount <= 1 ? minH
                                : minH + (maxH - minH) * Math.log(count) / Math.log(maxBarCount)}
                            {#if count > 0}
                                {@const rx = Math.min(0.45, h / 2)}
                                {@const ry = Math.min(3.0, h / 2)}
                                {@const x0 = i + 0.15}
                                {@const x1 = i + 0.85}
                                {@const yTop = 32 - h - 1}
                                <path
                                    d="M {x0},31 L {x0},{yTop + ry} Q {x0},{yTop} {x0 + rx},{yTop} L {x1 - rx},{yTop} Q {x1},{yTop} {x1},{yTop + ry} L {x1},31 Z"
                                    style="fill: {i < Math.floor(sliderValue * 100)
                                        ? 'var(--primary-color)'
                                        : isDarkMode ? 'rgba(255,255,255,0.25)' : 'rgba(0,0,0,0.18)'}"
                                />
                            {/if}
                        {/each}
                    </svg>
                </div>
                <div class="chart-bottom-border" aria-hidden="true"
                    style="background: linear-gradient(to right, var(--primary-color) {sliderValue * 100}%, {isDarkMode ? 'rgba(255,255,255,0.3)' : 'rgba(0,0,0,0.18)'} {sliderValue * 100}%)">
                </div>
                <input
                    type="range"
                    class="threshold-slider"
                    min="0"
                    max="1"
                    step="0.01"
                    bind:value={sliderValue}
                    disabled={loading}
                    aria-label="Chapter threshold: {selectedTimestamps.length} chapters selected at minimum gap {thresholdDisplay}"
                />
            </div>
            </div><!-- /.slider-bubble-area -->
            <div class="threshold-axis-labels">
                <span>Fewer chapters</span>
                <span class="threshold-drag-hint">← slide to adjust →</span>
                <span>More chapters</span>
            </div>

            <!-- Intro/Outro Sensitivity -->
            <div class="sensitivity-section">
                <div class="sensitivity-toggle-row">
                    <button
                        class="sensitivity-toggle"
                        on:click={() => (showSensitivity = !showSensitivity)}
                        aria-expanded={showSensitivity}
                        type="button"
                    >
                        Intro/Outro Sensitivity
                        <div
                            class="tooltip-container"
                            role="button"
                            tabindex="0"
                            on:mouseenter={() => (showSensitivityTooltip = true)}
                            on:mouseleave={() => (showSensitivityTooltip = false)}
                            on:focus={() => (showSensitivityTooltip = true)}
                            on:blur={() => (showSensitivityTooltip = false)}
                            aria-label="Sensitivity explanation"
                        >
                            <CircleQuestionMark size="13"/>
                            {#if showSensitivityTooltip}
                                <div class="sensitivity-tooltip">
                                    Adjusts the likelihood that cues near the start and end of the audiobook will be included.
                                </div>
                            {/if}
                        </div>
                        <div class="chevron {showSensitivity ? 'rotated' : ''}">
                            <ChevronDown size="12"/>
                        </div>
                    </button>
                </div>

                {#if showSensitivity}
                    <div class="sensitivity-content">
                        <div class="sensitivity-slider-row">
                            <span class="sensitivity-axis-label">Less</span>
                            <div class="sensitivity-slider-wrapper">
                                <input
                                    type="range"
                                    class="slider"
                                    min="-2"
                                    max="2"
                                    step="0.1"
                                    bind:value={sensitivity}
                                    disabled={loading}
                                    aria-label="Intro/outro sensitivity"
                                />
                                <div class="sensitivity-center-tick"></div>
                            </div>
                            <span class="sensitivity-axis-label">More</span>
                        </div>
                    </div>
                {/if}
            </div>
        </div>

        <!-- Include Unaligned Timestamps Options -->
        {#if existingCueSources.length > 0}
            <div class="unaligned-options" style:background={isDarkMode ? 'rgba(0,0,0,0.15)' : 'rgba(0,0,0,0.03)'}>
                <p class="unaligned-label">Include unaligned cues from:</p>
                <div class="unaligned-checkboxes">
                    {#each existingCueSources as source}
                        {@const unalignedCount = source.cues.filter(
                            cue => !selectedTimestamps.some(s => Math.abs(cue.timestamp - s) <= 5)
                        ).length}
                        <label class="checkbox-option">
                            <input
                                type="checkbox"
                                bind:checked={includeUnalignedSources[source.id]}
                                disabled={loading || unalignedCount === 0}
                            />
                            <span>{source.name} ({unalignedCount})</span>
                        </label>
                    {/each}
                </div>
            </div>
        {/if}

        <div class="actions">
            <button
                class="btn btn-verify"
                on:click={proceedWithSelection}
                disabled={selectedTimestamps.length === 0 || loading}
            >
                {#if loading}
                    <span class="btn-spinner"></span>
                    Processing...
                {:else if hasAdditionalTimestamps}
                    Create {totalChapterCount} Chapters
                {:else}
                    Create {selectedTimestamps.length} Chapters
                {/if}
            </button>
        </div>
    {/if}
</div>

<style>
    .chapter-selection {
        max-width: 900px;
        width: 100%;
        margin: 0 auto;
    }

    .header {
        text-align: center;
        margin-bottom: 2rem;
    }

    .header h2 {
        color: var(--text-primary);
        margin-bottom: 0.75rem;
        font-size: 2rem;
        font-weight: 600;
    }

    .header p {
        color: var(--text-secondary);
        font-size: 1rem;
        margin-bottom: 0.5rem;
    }

    /* ── Timeline ── */

    .timeline-visualization {
        background: var(--bg-secondary);
        border: 1px solid var(--border-color);
        border-radius: 8px;
        padding: 1.5rem 1.5rem 0.75rem 1.5rem;
        margin-bottom: 0.5rem;
    }

    .timeline-header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: 1rem;
        flex-wrap: wrap;
        gap: 1rem;
    }

    .timeline-visualization h4 {
        margin: 0;
        color: var(--text-primary);
        font-size: 1.1rem;
        display: flex;
        align-items: center;
    }

    .existing-chapter-toggles {
        display: flex;
        gap: 0.5rem;
    }

    .compare-label {
        font-size: 0.875rem;
        color: var(--compare-accent);
        margin-right: 0.5rem;
        display: flex;
        align-items: center;
        gap: 0.25rem;
    }

    .toggle-btn {
        padding: 0.25rem 0.75rem;
        font-size: 0.75rem;
        font-weight: 600;
        border: 1px solid var(--compare-accent);
        background: transparent;
        color: var(--compare-accent);
        border-radius: 4px;
        cursor: pointer;
        transition: all 0.2s ease;
        text-transform: uppercase;
    }

    .toggle-btn:hover {
        background: color-mix(in srgb, var(--compare-accent) 12%, transparent);
        transform: translateY(-1px);
    }

    .toggle-btn.active {
        background: var(--compare-accent);
        color: var(--bg-primary);
    }

    .timeline-container {
        position: relative;
    }

    .timeline-labels {
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-top: 0.75rem;
        font-size: 0.875rem;
        color: var(--text-secondary);
        font-family: monospace;
        font-weight: 600;
    }

    .alignment-text {
        font-size: 0.75rem;
        font-weight: 600;
        font-family: monospace;
        text-align: center;
        flex: 1;
    }

    .timeline-track {
        position: relative;
        height: 32px;
    }

    .timeline-line {
        position: absolute;
        top: 50%;
        left: 0;
        right: 0;
        height: 1px;
        background: var(--primary-contrast);
        transform: translateY(-50%);
        transition: all 0.2s ease;
    }

    .timeline-line.compared {
        top: calc(100% - 8px);
        height: 0.05rem;
    }

    .timeline-ticks {
        position: absolute;
        top: 0;
        left: 0;
        right: 0;
        height: 100%;
    }

    .timeline-tick {
        position: absolute;
        top: 50%;
        width: 2px;
        height: 16px;
        background: var(--primary-contrast);
        transform: translate(-50%, -50%);
        cursor: pointer;
        border-radius: 1px;
        transition: top 0.2s ease, height 0.2s ease, background 0.2s ease, transform 0.2s ease;
    }

    .timeline-tick.compared {
        top: 100%;
        height: 16px;
        background: var(--text-primary);
        transform: translate(-50%, -16px);
    }

    .timeline-tick.compared.aligned {
        top: 100%;
        height: 10px;
        background: var(--primary-contrast);
        transform: translate(-50%, -13px);
    }

    .timeline-tick:hover {
        height: 16px;
        background: var(--primary-hover);
        transform: translate(-50%, -50%) scaleX(1.5);
    }

    .timeline-tick:first-child {
        display: none;
    }

    .existing-timeline-line {
        position: absolute;
        top: 6px;
        left: 0;
        right: 0;
        height: 1px;
        background: color-mix(in srgb, var(--compare-accent) 50%, transparent);
    }

    .existing-timeline-tick {
        position: absolute;
        width: 3px;
        height: 16px;
        transform: translate(-50%, -2px);
        background-color: var(--danger);
        cursor: pointer;
        border-radius: 1px;
        transition: all 0.2s ease;
    }

    .existing-timeline-tick.aligned {
        width: 1px;
        height: 8px;
        transform: translate(-50%, 2px);
        background-color: var(--compare-accent);
    }

    .existing-timeline-tick:hover {
        height: 16px;
        transform: translate(-50%) scaleX(1.5);
    }

    /* ── Threshold Slider ── */

    .threshold-section {
        padding: 1.5rem 1.5rem;
        margin-bottom: 0.5rem;
    }

    .slider-bubble-area {
        position: relative;
        padding-top: 3rem;
    }

    .selected-bubble {
        position: absolute;
        top: 0;
        transform: translateX(-50%);
        display: flex;
        flex-direction: column;
        align-items: center;
        pointer-events: none;
        z-index: 10;
    }

    .bubble-content {
        background: var(--primary-color);
        color: white;
        padding: 0.4rem 0.7rem;
        border-radius: 8px;
        white-space: nowrap;
        display: flex;
        flex-direction: column;
        align-items: center;
    }

    .bubble-main {
        display: flex;
        align-items: baseline;
        gap: 0.25rem;
        line-height: 1.3;
    }

    .bubble-number {
        font-size: 1.125rem;
        font-weight: 700;
    }

    .bubble-cues-label {
        font-size: 0.75rem;
        font-weight: 500;
        opacity: 0.85;
    }

    .bubble-tail {
        width: 0;
        height: 0;
        border-left: 7px solid transparent;
        border-right: 7px solid transparent;
        border-top: 7px solid var(--primary-color);
        margin-top: -1px;
    }

    .bar-chart-wrapper {
        position: relative;
        height: 42px;
        border-radius: 6px;
        overflow: hidden;
    }

    .bar-chart-svg-container {
        position: absolute;
        inset: 0;
        pointer-events: none;
    }

    .bar-chart-svg {
        width: 100%;
        height: 100%;
        display: block;
    }

    .chart-bottom-border {
        position: absolute;
        bottom: 0;
        left: 0;
        right: 0;
        height: 2px;
        pointer-events: none;
    }

    .threshold-slider {
        position: absolute;
        top: 0;
        left: 0;
        width: 100%;
        height: 100%;
        appearance: none;
        -webkit-appearance: none;
        background: transparent;
        cursor: pointer;
        margin: 0;
        padding: 0;
    }

    .threshold-slider:disabled {
        cursor: not-allowed;
        opacity: 0.5;
    }

    .threshold-slider::-webkit-slider-runnable-track {
        height: 42px;
        background: transparent;
    }

    .threshold-slider::-moz-range-track {
        height: 42px;
        background: transparent;
        border: none;
    }

    .threshold-slider::-webkit-slider-thumb {
        -webkit-appearance: none;
        appearance: none;
        width: 4px;
        height: 50px;
        background: white;
        border-radius: 2px;
        margin-top: -4px;
        box-shadow: 0 0 0 1px rgba(0, 0, 0, 0.15), 0 1px 6px rgba(0, 0, 0, 0.2);
        cursor: pointer;
        transition: width 0.1s ease, background 0.1s ease;
    }

    .threshold-slider:not(:disabled):hover::-webkit-slider-thumb,
    .threshold-slider:not(:disabled):focus::-webkit-slider-thumb {
        width: 5px;
        background: var(--primary-color);
    }

    .threshold-slider::-moz-range-thumb {
        width: 4px;
        height: 50px;
        background: white;
        border-radius: 2px;
        border: none;
        box-shadow: 0 0 0 1px rgba(0, 0, 0, 0.15), 0 1px 6px rgba(0, 0, 0, 0.2);
        cursor: pointer;
    }

    .threshold-axis-labels {
        display: flex;
        justify-content: space-between;
        margin-top: 0.4rem;
        font-size: 0.75rem;
        color: var(--text-muted);
    }

    .threshold-drag-hint {
        font-style: italic;
        opacity: 0.7;
    }

    /* ── Sensitivity Section ── */

    .sensitivity-section {
        margin-top: 1.5rem;
        display: flex;
        flex-direction: column;
        align-items: center;
    }

    .sensitivity-toggle-row {
        display: inline-flex;
        align-items: center;
        gap: 0.35rem;
        color: var(--text-muted);
    }

    .sensitivity-toggle {
        display: inline-flex;
        align-items: center;
        gap: 0.4rem;
        background: none;
        border: none;
        color: inherit;
        font-size: 0.85rem;
        font-weight: 500;
        cursor: pointer;
        padding: 0.25rem 0;
        transition: color 0.2s ease;
    }

    .sensitivity-toggle-row:hover {
        color: var(--text-primary);
    }

    .sensitivity-content {
        margin-top: 0.75rem;
        display: flex;
        flex-direction: column;
        gap: 0.5rem;
        align-items: center;
        width: 100%;
    }

    .sensitivity-slider-row {
        display: flex;
        align-items: center;
        gap: 0.75rem;
        width: 100%;
    }

    .sensitivity-slider-wrapper {
        flex: 1;
        position: relative;
        display: flex;
        align-items: center;
    }

    .sensitivity-slider-wrapper .slider {
        width: 100%;
    }

    .sensitivity-center-tick {
        position: absolute;
        left: 50%;
        top: 50%;
        width: 2px;
        height: 8px;
        background: var(--text-muted);
        transform: translate(-50%, 8px);
        opacity: 0.45;
        pointer-events: none;
        border-radius: 1px;
    }

    .sensitivity-tooltip {
        position: absolute;
        top: 100%;
        left: 50%;
        transform: translateX(-50%);
        margin-top: 0.5rem;
        background: var(--bg-primary);
        border: 1px solid var(--border-color);
        border-radius: 8px;
        padding: 0.75rem 1rem;
        z-index: 1000;
        width: 280px;
        font-size: 0.8rem;
        line-height: 1.5;
        color: var(--text-secondary);
        white-space: normal;
        text-align: left;
        box-shadow: 0 2px 8px rgba(0,0,0,0.1);
        pointer-events: none;
    }

    .sensitivity-axis-label {
        font-size: 0.75rem;
        color: var(--text-muted);
        white-space: nowrap;
        flex-shrink: 0;
    }

    /* Reuse the standard slider style from the rest of the app */
    .slider {
        flex: 1;
        height: 6px;
        border-radius: 3px;
        background: var(--bg-tertiary);
        outline: none;
        appearance: none;
        cursor: pointer;
        -webkit-appearance: none;
    }

    .slider::-webkit-slider-thumb {
        appearance: none;
        -webkit-appearance: none;
        width: 18px;
        height: 18px;
        border-radius: 50%;
        background: var(--primary-color);
        cursor: pointer;
        transition: all 0.2s ease;
    }

    .slider::-webkit-slider-thumb:hover {
        transform: scale(1.1);
    }

    .slider::-moz-range-thumb {
        width: 18px;
        height: 18px;
        border-radius: 50%;
        background: var(--primary-color);
        cursor: pointer;
        border: none;
        transition: all 0.2s ease;
    }

    .slider::-moz-range-thumb:hover {
        transform: scale(1.1);
    }

    /* ── Unaligned Options ── */

    .unaligned-options {
        padding: 1rem 1.5rem;
        margin: 0 auto 2rem auto;
        border-radius: 8px;
        width: fit-content;
    }

    .unaligned-label {
        font-size: 0.875rem;
        color: var(--text-secondary);
        margin: 0 0 0.5rem 0;
        text-align: center;
    }

    .unaligned-checkboxes {
        display: flex;
        flex-direction: row;
        flex-wrap: wrap;
        justify-content: center;
        gap: 0.5rem 1.25rem;
    }

    .checkbox-option {
        display: flex;
        align-items: center;
        gap: 0.5rem;
        cursor: pointer;
        font-size: 0.9rem;
        color: var(--text-primary);
        transition: color 0.2s ease;
    }

    .checkbox-option:hover {
        color: var(--primary-color);
    }

    .checkbox-option input[type="checkbox"] {
        margin: 0;
        cursor: pointer;
        transform: scale(1.1);
        flex-shrink: 0;
    }

    .checkbox-option input[type="checkbox"]:disabled {
        cursor: not-allowed;
        opacity: 0.6;
    }

    .checkbox-option:has(input[type="checkbox"]:disabled) {
        cursor: not-allowed;
        opacity: 0.6;
    }

    /* ── Actions ── */

    .actions {
        display: flex;
        justify-content: center;
        margin-bottom: 1rem;
    }

    /* ── Empty / Loading States ── */

    .empty-state {
        text-align: center;
        padding: 4rem 2rem;
        color: var(--text-secondary);
    }

    .empty-icon {
        font-size: 4rem;
        margin-bottom: 1rem;
    }

    .spinner {
        width: 16px;
        height: 16px;
        border: 2px solid transparent;
        border-radius: 50%;
        animation: spin 1s linear infinite;
        display: inline-block;
        margin-right: 0.5rem;
    }

    @keyframes spin {
        0% { transform: rotate(0deg); }
        100% { transform: rotate(360deg); }
    }

    .float-right {
        float: right;
        margin-left: 1rem;
    }

    /* ── Usage Hints ── */

    .usage-hints-section {
        margin-top: 0.5rem;
        text-align: center;
    }

    .usage-hints-toggle {
        display: inline-flex;
        align-items: center;
        gap: 0.5rem;
        background: none;
        border: none;
        color: var(--text-muted);
        font-size: 0.9rem;
        font-weight: 500;
        cursor: pointer;
        padding: 0.5rem 0;
        transition: color 0.2s ease;
    }

    .usage-hints-toggle:hover {
        color: var(--text-primary);
    }

    .chevron {
        display: inline-flex;
        flex-shrink: 0;
        transition: transform 0.2s ease;
    }

    .chevron.rotated {
        transform: rotate(180deg);
    }

    .usage-hints-content {
        margin-top: 0.5rem;
        border: 1px solid var(--border-color);
        border-radius: 8px;
        padding: 1.5rem;
        animation: fadeIn 0.3s ease;
        text-align: left;
    }

    .hints-list {
        list-style: none;
        padding: 0;
        margin: 0;
    }

    .hints-list p {
        margin-top: 0.5rem;
    }

    .hints-list li {
        margin-bottom: 1rem;
        line-height: 1.5;
        color: var(--text-secondary);
    }

    .hints-list li:last-child {
        margin-bottom: 0;
    }

    .hints-list strong {
        color: var(--text-primary);
    }

    @keyframes fadeIn {
        from { opacity: 0; transform: translateY(-10px); }
        to { opacity: 1; transform: translateY(0); }
    }

    /* ── Tooltips ── */

    .tooltip-container {
        position: relative;
        display: inline-flex;
        align-items: center;
        cursor: help;
    }

    .tooltip-container :global(.help-icon) {
        pointer-events: none;
    }

    .tooltip-container :global(.icon) {
        pointer-events: none;
    }

    .tooltip {
        position: absolute;
        top: 100%;
        left: 50%;
        transform: translateX(-50%);
        margin-top: 0.5rem;
        background: var(--bg-primary);
        border: 1px solid var(--border-color);
        border-radius: 8px;
        padding: 1rem;
        z-index: 1000;
        width: 360px;
        font-size: 0.875rem;
        line-height: 1.4;
    }

    .tooltip-header {
        font-weight: 600;
        color: var(--text-primary);
        margin-bottom: 0.75rem;
        text-align: center;
        border-bottom: 1px solid var(--border-color);
        padding-bottom: 0.5rem;
    }

    .tooltip-content {
        display: flex;
        flex-direction: column;
        gap: 0.75rem;
    }

    .legend-item {
        display: flex;
        align-items: center;
        gap: 0.75rem;
    }

    .legend-visual {
        flex-shrink: 0;
        width: 32px;
        height: 20px;
    }

    .legend-text {
        color: var(--text-secondary);
        font-size: 0.8rem;
    }

    .legend-text strong {
        color: var(--text-primary);
    }

    .mini-timeline {
        position: relative;
        width: 100%;
        height: 100%;
    }

    .mini-timeline-line {
        position: absolute;
        top: 6px;
        left: 0;
        right: 0;
        height: 1px;
        background: color-mix(in srgb, var(--compare-accent) 50%, transparent);
    }

    .mini-timeline-line.bottom {
        top: 14px;
        background: var(--primary-contrast);
    }

    .mini-tick {
        position: absolute;
        width: 2px;
        height: 8px;
        border-radius: 1px;
        transform: translateX(-50%);
    }

    .mini-tick.existing.unaligned {
        top: 2px;
        background: var(--danger);
    }

    .mini-tick.existing.aligned {
        top: 6px;
        background: var(--compare-accent);
        height: 6px;
        transform: translate(-50%, -50%);
    }

    .mini-tick.new.unaligned {
        top: 10px;
        background: var(--text-primary);
    }

    .mini-tick.new.aligned {
        top: 12px;
        background: var(--primary-contrast);
        height: 7px;
        transform: translate(-50%, -1px);
    }

    .timeline-tooltip {
        position: absolute;
        background: var(--bg-primary);
        color: var(--text-primary);
        border: 1px solid var(--border-color);
        border-radius: 6px;
        padding: 0.375rem 0.5rem;
        font-size: 0.75rem;
        font-family: monospace;
        font-weight: 600;
        white-space: nowrap;
        z-index: 100;
        pointer-events: none;
        box-shadow: 0 2px 8px rgba(0, 0, 0, 0.05);
        transform: translateX(-50%);
        animation: fadeInTooltip 0.2s ease;
    }

    .timeline-tooltip-top {
        bottom: calc(100% + 8px);
    }

    .timeline-tooltip-bottom {
        top: calc(100% + 8px);
    }

    .timeline-tooltip::after {
        content: '';
        position: absolute;
        left: 50%;
        transform: translateX(-50%);
        border: 5px solid transparent;
    }

    .timeline-tooltip-top::after {
        top: 100%;
        border-top-color: var(--border-color);
    }

    .timeline-tooltip-bottom::after {
        bottom: 100%;
        border-bottom-color: var(--border-color);
    }

    .timeline-tooltip::before {
        content: '';
        position: absolute;
        left: 50%;
        transform: translateX(-50%);
        border: 4px solid transparent;
        z-index: 1;
    }

    .timeline-tooltip-top::before {
        top: 100%;
        border-top-color: var(--bg-primary);
    }

    .timeline-tooltip-bottom::before {
        bottom: 100%;
        border-bottom-color: var(--bg-primary);
    }

    /* ── Responsive ── */

    @media (max-width: 768px) {
        .chapter-selection {
            padding: 1rem;
        }

        .header h2 {
            font-size: 1.5rem;
        }

        .timeline-visualization {
            padding: 1rem 1rem 0.5rem 1rem;
        }

        .timeline-header {
            flex-direction: column;
            align-items: flex-start;
            gap: 0.75rem;
        }

        .timeline-visualization h4 {
            font-size: 1rem;
        }

        .existing-chapter-toggles {
            align-self: stretch;
            justify-content: flex-end;
        }

        .toggle-btn {
            font-size: 0.7rem;
            padding: 0.2rem 0.6rem;
        }

        .actions .btn {
            min-width: 200px;
            font-size: 1rem;
        }

        .usage-hints-section {
            margin-top: 1rem;
        }

        .usage-hints-toggle {
            font-size: 0.85rem;
        }

        .usage-hints-content {
            padding: 1rem;
        }

        .hints-list li {
            font-size: 0.9rem;
            margin-bottom: 0.875rem;
        }

        .tooltip {
            width: 250px;
            font-size: 0.8rem;
            padding: 0.875rem;
        }

        .legend-visual {
            width: 50px;
            height: 16px;
        }

        .legend-text {
            font-size: 0.75rem;
        }

        .tooltip-container {
            margin-left: 0.2rem;
        }

        .timeline-tooltip {
            font-size: 0.7rem;
            padding: 0.3rem 0.4rem;
        }

        .sensitivity-slider-row {
            gap: 0.5rem;
        }
    }
</style>
