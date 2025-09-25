<script>
    import {onDestroy, onMount} from "svelte";
    import {session} from "../stores/session.js";
    import {api} from "../utils/api.js";

    // Icons
    import BookDashed from "@lucide/svelte/icons/book-dashed";
    import ChevronDown from "@lucide/svelte/icons/chevron-down";
    import CircleQuestionMark from "@lucide/svelte/icons/circle-question-mark";
    import Clock4 from "@lucide/svelte/icons/clock-4";

    let loading = false;
    let selectedOption = null;
    let cueSets = [];
    let bookDuration = 0;
    let error = null;
    let sliderValue = 0; // Index in cueSets array
    let trackElement;
    let isDragging = false;
    let existingCueSources = [];
    let activeComparisonSource = null;
    let showUsageHints = false;
    let includeUnalignedSources = {};
    let showTooltip = false;
    
    let timelineTooltip = {
        show: false,
        showTop: false,
        showBottom: false,
        x: 0,
        topContent: '',
        bottomContent: ''
    };

    $: innerWidth = 0

    // Track theme for conditional text
    let isDarkMode = false;

    // Update theme status when component mounts or theme changes
    function updateThemeStatus() {
        if (typeof document !== "undefined") {
            isDarkMode =
                document.documentElement.getAttribute("data-theme") === "dark";
        }
    }

    // Set up theme detection
    onMount(() => {
        updateThemeStatus();

        // Watch for theme changes
        const observer = new MutationObserver((mutations) => {
            mutations.forEach((mutation) => {
                if (
                    mutation.type === "attributes" &&
                    mutation.attributeName === "data-theme"
                ) {
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

    $: isComparing = activeComparisonSource !== null;

    onMount(async () => {
        await loadCueSets();
    });

    onDestroy(() => {
        // Clean up document event listeners if component is destroyed while dragging
        document.removeEventListener("mousemove", handleDocumentMouseMove);
        document.removeEventListener("mouseup", handleDocumentMouseUp);
        document.removeEventListener("touchmove", handleDocumentTouchMove);
        document.removeEventListener("touchend", handleDocumentTouchEnd);
    });

    async function loadCueSets() {
        if ($session.step !== "cue_set_selection") return;

        loading = true;
        error = null;

        try {
            const response = await api.session.getCueSets();
            cueSets = response.cue_sets;
            bookDuration = response.book_duration;
            existingCueSources = response.existing_cue_sources || [];

            // Initialize includeUnalignedSources object for all existing sources
            includeUnalignedSources = {};
            existingCueSources.forEach((source) => {
                includeUnalignedSources[source.id] = false;
            });

            // Initial selection logic:
            // 1. Try highest existing chapter count (closest but greater than highest existing)
            // 2. Fall back to middle option

            // Find the highest count from existing cue sources
            let highestExistingCount = 0;
            existingCueSources.forEach((source) => {
                if (source.cues && source.cues.length > 0) {
                    highestExistingCount = Math.max(
                        highestExistingCount,
                        source.cues.length,
                    );
                }
            });

            if (highestExistingCount > 0) {
                // Find the closest option that is greater than the highest existing count
                const existingBasedOption = cueSets
                    .filter((opt) => opt.chapter_count > highestExistingCount)
                    .sort((a, b) => a.chapter_count - b.chapter_count)[0];

                if (existingBasedOption) {
                    const existingIndex = cueSets.findIndex(
                        (opt) => opt.chapter_count === existingBasedOption.chapter_count,
                    );
                    sliderValue = existingIndex;
                    selectedOption = existingBasedOption.chapter_count;
                }
            }

            // Fallback to middle option
            if (selectedOption === null && cueSets.length > 0) {
                const middleIndex = Math.floor(cueSets.length / 2);
                sliderValue = middleIndex;
                selectedOption = cueSets[middleIndex].chapter_count;
            }
        } catch (err) {
            error = `Failed to load cue sets: ${err.message}`;
            console.error("Error loading cue sets:", err);
        } finally {
            loading = false;
        }
    }

    async function proceedWithSelection() {
        if (!selectedOption) {
            alert("Please select a cue set");
            return;
        }

        loading = true;
        error = null;

        try {
            // Determine which options are selected using the new structure
            const unalignedOptions = [];
            Object.keys(includeUnalignedSources).forEach((sourceId) => {
                if (includeUnalignedSources[sourceId]) {
                    unalignedOptions.push(sourceId);
                }
            });

            await api.session.selectCueSet(selectedOption, unalignedOptions);
        } catch (err) {
            error = `Failed to select cue set: ${err.message}`;
            console.error("Error selecting cue set:", err);
        } finally {
            loading = false;
        }
    }

    // Format time for display
    function formatTime(minutes) {
        if (minutes < 60) {
            return `${Math.round(minutes)}m`;
        }
        const hours = Math.floor(minutes / 60);
        const mins = Math.round(minutes % 60);
        return `${hours}h ${mins}m`;
    }

    // Format time for timeline display (HH:MM or MM:SS format)
    function formatTimelineTime(seconds) {
        const hours = Math.floor(seconds / 3600);
        const minutes = Math.floor((seconds % 3600) / 60);
        const secs = Math.floor(seconds % 60);

        if (hours > 0) {
            return `${hours}:${minutes.toString().padStart(2, "0")}:${secs.toString().padStart(2, "0")}`;
        } else {
            return `${minutes}:${secs.toString().padStart(2, "0")}`;
        }
    }

    // Toggle existing cue source display
    function toggleCueSourceDisplay(sourceId) {
        if (activeComparisonSource === sourceId) {
            activeComparisonSource = null;
        } else {
            activeComparisonSource = sourceId;
        }
    }

    // Check if an existing chapter timestamp aligns with any selected chapter timestamp
    function isChapterAligned(
        existingTimestamp,
        selectedTimestamps,
        tolerance = 5,
    ) {
        return selectedTimestamps.some(
            (timestamp) => Math.abs(existingTimestamp - timestamp) <= tolerance,
        );
    }

    // Calculate alignment percentage between existing chapters and selected chapters
    function calculateAlignmentPercentage(
        existingTimestamps,
        selectedTimestamps,
    ) {
        if (
            !existingTimestamps ||
            !selectedTimestamps ||
            existingTimestamps.length === 0
        ) {
            return 0;
        }

        const alignedCount = existingTimestamps.filter((timestamp) =>
            isChapterAligned(timestamp, selectedTimestamps),
        ).length;

        return Math.round((alignedCount / existingTimestamps.length) * 100);
    }

    // Get color for alignment percentage with three ranges using CSS custom properties
    function getAlignmentColor(percentage) {
        if (percentage <= 50) {
            // 0% to 50%: red
            return "var(--danger)";
        } else if (percentage <= 75) {
            // 50% to 75%: fade from red to warning
            const t = (percentage - 50) / 25; // Normalize to 0-1 range
            // Create a CSS custom property interpolation using color-mix if supported, otherwise fallback
            if (CSS.supports("color", "color-mix(in srgb, red 50%, blue 50%)")) {
                const redWeight = Math.round((1 - t) * 100);
                const warningWeight = Math.round(t * 100);
                return `color-mix(in srgb, var(--danger) ${redWeight}%, var(--warning) ${warningWeight}%)`;
            } else {
                // Fallback: return warning color for this range
                return "var(--warning)";
            }
        } else {
            // 75% to 100%: fade from warning to primary-contrast
            const t = Math.min((percentage - 75) / 25, 1); // Normalize to 0-1 range, cap at 1 for 100%
            // Create a CSS custom property interpolation using color-mix if supported, otherwise fallback
            if (CSS.supports("color", "color-mix(in srgb, red 50%, blue 50%)")) {
                const warningWeight = Math.round((1 - t) * 100);
                const primaryWeight = Math.round(t * 100);
                return `color-mix(in srgb, var(--warning) ${warningWeight}%, var(--primary-contrast) ${primaryWeight}%)`;
            } else {
                // Fallback: return primary-contrast for this range
                return "var(--primary-contrast)";
            }
        }
    }

    // Get visual width for timeline
    function getTimelineWidth(chapterCount) {
        if (cueSets.length === 0) return "0%";
        const minCount = Math.min(...cueSets.map((opt) => opt.chapter_count));
        const maxCount = Math.max(...cueSets.map((opt) => opt.chapter_count));
        if (maxCount === minCount) return "100%";

        const range = maxCount - minCount;
        const position = (chapterCount - minCount) / range;
        return `${Math.max(20, position * 80 + 10)}%`;
    }

    // Handle stop click
    function handleStopClick(index) {
        sliderValue = index;
        if (cueSets[index]) {
            selectedOption = cueSets[index].chapter_count;
        }
    }

    // Find closest option based on click position
    function findClosestOption(clickPercentage) {
        if (cueSets.length === 0) return 0;

        let closestIndex = 0;
        let closestDistance = Infinity;

        cueSets.forEach((option, index) => {
            const optionPosition = getProportionalPosition(option.chapter_count);
            const distance = Math.abs(clickPercentage - optionPosition);
            if (distance < closestDistance) {
                closestDistance = distance;
                closestIndex = index;
            }
        });

        return closestIndex;
    }

    // Handle track mouse events
    function handleTrackMouseDown(event) {
        if (loading) return;
        isDragging = true;
        handleTrackClick(event);

        // Add document-level event listeners for drag tracking
        document.addEventListener("mousemove", handleDocumentMouseMove);
        document.addEventListener("mouseup", handleDocumentMouseUp);
    }

    function handleDocumentMouseMove(event) {
        if (!isDragging || loading) return;
        handleTrackClick(event);
    }

    function handleDocumentMouseUp() {
        isDragging = false;
        // Remove document-level event listeners
        document.removeEventListener("mousemove", handleDocumentMouseMove);
        document.removeEventListener("mouseup", handleDocumentMouseUp);
    }

    // Handle track touch events
    function handleTrackTouchStart(event) {
        if (loading) return;
        event.preventDefault(); // Prevent scrolling while dragging
        isDragging = true;
        handleTrackTouch(event);

        // Add document-level event listeners for drag tracking
        document.addEventListener("touchmove", handleDocumentTouchMove, {passive: false});
        document.addEventListener("touchend", handleDocumentTouchEnd);
    }

    function handleDocumentTouchMove(event) {
        if (!isDragging || loading) return;
        event.preventDefault(); // Prevent scrolling while dragging
        handleTrackTouch(event);
    }

    function handleDocumentTouchEnd() {
        isDragging = false;
        // Remove document-level event listeners
        document.removeEventListener("touchmove", handleDocumentTouchMove);
        document.removeEventListener("touchend", handleDocumentTouchEnd);
    }

    function handleTrackClick(event) {
        if (!trackElement) return;

        const rect = trackElement.getBoundingClientRect();
        const clickX = event.clientX - rect.left;
        const clickPercentage = (clickX / rect.width) * 100;

        // Clamp to bounds
        const clampedPercentage = Math.max(0, Math.min(100, clickPercentage));

        const closestIndex = findClosestOption(clampedPercentage);
        handleStopClick(closestIndex);
    }

    function handleTrackTouch(event) {
        if (!trackElement) return;

        const rect = trackElement.getBoundingClientRect();
        const touch = event.touches[0] || event.changedTouches[0];
        const touchX = touch.clientX - rect.left;
        const touchPercentage = (touchX / rect.width) * 100;

        // Clamp to bounds
        const clampedPercentage = Math.max(0, Math.min(100, touchPercentage));

        const closestIndex = findClosestOption(clampedPercentage);
        handleStopClick(closestIndex);
    }

    // Handle keyboard navigation for accessibility
    function handleKeyDown(event) {
        if (loading || cueSets.length === 0) return;

        switch (event.key) {
            case "ArrowLeft":
            case "ArrowDown":
                event.preventDefault();
                if (sliderValue > 0) {
                    handleStopClick(sliderValue - 1);
                }
                break;
            case "ArrowRight":
            case "ArrowUp":
                event.preventDefault();
                if (sliderValue < cueSets.length - 1) {
                    handleStopClick(sliderValue + 1);
                }
                break;
            case "Home":
                event.preventDefault();
                handleStopClick(0);
                break;
            case "End":
                event.preventDefault();
                handleStopClick(cueSets.length - 1);
                break;
            case "Enter":
            case " ":
                event.preventDefault();
                // Space or Enter could trigger selection confirmation
                break;
        }
    }

    // Get the current selected option details
    $: currentOption =
        cueSets.length > 0 && sliderValue >= 0 && sliderValue < cueSets.length
            ? cueSets[sliderValue]
            : null;

    // Check if a chapter set is fully aligned with current selection
    function isFullyAligned(existingTimestamps, selectedTimestamps) {
        if (
            !existingTimestamps ||
            !selectedTimestamps ||
            existingTimestamps.length === 0 ||
            selectedTimestamps.length === 0
        ) {
            return false; // Can't be aligned if either set is empty
        }

        const alignmentPercentage = calculateAlignmentPercentage(
            existingTimestamps,
            selectedTimestamps,
        );
        return alignmentPercentage >= 100;
    }

    // Get proportional position based on chapter count value
    function getProportionalPosition(chapterCount) {
        if (cueSets.length === 0) return 0;
        const minCount = Math.min(...cueSets.map((opt) => opt.chapter_count));
        const maxCount = Math.max(...cueSets.map((opt) => opt.chapter_count));
        if (maxCount === minCount) return 50; // Center if all values are the same

        const range = maxCount - minCount;
        const position = (chapterCount - minCount) / range;
        return position * 100;
    }

    // Calculate number of additional timestamps that will be added
    function getAdditionalTimestampCount() {
        if (!currentOption || !existingCueSources.length) return 0;

        let count = 0;
        const tolerance = 5.0;

        existingCueSources.forEach((source) => {
            if (includeUnalignedSources[source.id]) {
                const unaligned = source.cues.filter(
                    (cue) =>
                        !currentOption.timestamps.some(
                            (selected) => Math.abs(cue.timestamp - selected) <= tolerance,
                        ),
                );
                count += unaligned.length;
            }
        });

        return count;
    }

    // Calculate total chapter count for button text
    $: totalChapterCount = selectedOption + getAdditionalTimestampCount();
    $: hasAdditionalTimestamps = Object.values(includeUnalignedSources).some(
        (value) => value === true,
    );

    function handleTimelineMouseMove(event) {
        if (!currentOption || !currentOption.timestamps) return;
        
        const timelineTrack = event.currentTarget;
        const rect = timelineTrack.getBoundingClientRect();
        const mouseX = event.clientX - rect.left;
        const timelineWidth = rect.width;
        const mousePercent = (mouseX / timelineWidth) * 100;
        
        let nearestTick = null;
        let nearestDistance = Infinity;
        
        currentOption.timestamps.forEach((timestamp, index) => {
            if (index === 0) return;
            
            const tickPercent = (timestamp / bookDuration) * 100;
            const distance = Math.abs(mousePercent - tickPercent);
            if (distance < nearestDistance) {
                nearestDistance = distance;
                nearestTick = {
                    type: 'new',
                    timestamp,
                    index,
                    percent: tickPercent
                };
            }
        });
        
        if (activeComparisonSource) {
            const activeSource = existingCueSources.find(
                (source) => source.id === activeComparisonSource,
            );
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
                    if (nearestTick.source.id === 'file_starts') {
                        timelineTooltip.topContent = `File Start: ${formatTimelineTime(nearestTick.timestamp)}`;
                    } else {
                        timelineTooltip.topContent = `${nearestTick.source.short_name} Chapter: ${formatTimelineTime(nearestTick.timestamp)}`;
                    }
                    timelineTooltip.showTop = true;
                    
                    const alignedNewTick = currentOption.timestamps.find(ts =>
                        Math.abs(ts - nearestTick.timestamp) <= 5
                    );
                    if (alignedNewTick) {
                        timelineTooltip.bottomContent = formatTimelineTime(alignedNewTick);
                        timelineTooltip.showBottom = true;
                    } else {
                        timelineTooltip.showBottom = false;
                    }
                } else {
                    timelineTooltip.bottomContent = formatTimelineTime(nearestTick.timestamp);
                    timelineTooltip.showBottom = true;
                    
                    const activeSource = existingCueSources.find(
                        (source) => source.id === activeComparisonSource,
                    );
                    if (activeSource) {
                        const alignedExistingTick = activeSource.cues.find(cue =>
                            Math.abs(cue.timestamp - nearestTick.timestamp) <= 5
                        );
                        if (alignedExistingTick) {
                            if (activeSource.id === 'file_starts') {
                                timelineTooltip.topContent = `File Start: ${formatTimelineTime(alignedExistingTick.timestamp)}`;
                            } else {
                                timelineTooltip.topContent = `${activeSource.short_name} Chapter: ${formatTimelineTime(alignedExistingTick.timestamp)}`;
                            }
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
        <h2>Select Cue Set</h2>
        <p>
            We've found <strong
        >{cueSets.length > 0
            ? Math.max(...cueSets.map((opt) => opt.chapter_count))
            : "X"}</strong
        >
            potential chapter cues and have grouped them into
            <strong>{cueSets.length}</strong>
            sets of increasing cue count.<br/>
            Use the slider below to select an appropriate set of cues for your audiobook.
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
                            <strong>Timeline:</strong> Use the timeline below to visualize how
                            the selected set of cues are distributed throughout the audiobook.
                        </li>
                        <li>
                            <strong>Distribution:</strong> Many books are likely to have a
                            <i>somewhat</i> even distribution of cues. Aim for a balanced distribution
                            by selecting a larger set if there are large gaps, or selecting a smaller
                            set if there are numerous tight clusters.
                        </li>
                        <li>
                            <strong>Alignment:</strong> If existing chapter information is available
                            from a source that you believe has accurate timestamps (embedded/Audnexus/etc),
                            aim for a high alignment % with that source.
                        </li>
                        <li>
                            <strong>Intro/Outro:</strong> Many books have special sections (intro/outro,
                            prologue/epilogue, credits, bloopers, etc). Look for sets that have
                            cues near the very start and very end of the timeline.
                        </li>
                        <li>
                            <strong>Don't Sweat It:</strong> No need to get it perfect right now; you can add
                            and delete chapters in a future step. Just aim for a balanced starting point, 
                            bump it up a notch or two for good measure, and worry about refining it later.
                        </li>
                    </ul>
                </div>
            {/if}
        </div>
    </div>

    {#if loading && cueSets.length === 0}
        <div class="text-center p-4">
            <div class="spinner"></div>
            <p class="mt-2">Analyzing cue sets...</p>
        </div>
    {:else if cueSets.length === 0}
        <div class="empty-state">
            <div class="empty-icon">
                <BookDashed size="48"/>
            </div>
            <h3>No cue sets available</h3>
            <p>Unable to generate any cue sets from the audio analysis.</p>
        </div>
    {:else}
        <!-- Timeline Visualization -->
        {#if currentOption && currentOption.timestamps}
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
                                                            <div
                                                                    class="mini-tick existing unaligned"
                                                                    style="left: 50%"
                                                            ></div>
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
                                                            <div
                                                                    class="mini-tick new unaligned"
                                                                    style="left: 50%"
                                                            ></div>
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
                                                            <div
                                                                    class="mini-tick existing aligned"
                                                                    style="left: 50%"
                                                            ></div>
                                                            <div
                                                                    class="mini-tick new aligned"
                                                                    style="left: 50%"
                                                            ></div>
                                                        </div>
                                                    </div>
                                                    <div class="legend-text">
                                                        {#if isDarkMode}
                                                            <strong>Yellow/Green ticks:</strong> Aligned cues (both
                                                            sources match)
                                                        {:else}
                                                            <strong>Blue/Purple ticks:</strong> Aligned cues (both
                                                            sources match)
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
                            {@const activeSource = existingCueSources.find(
                                (source) => source.id === activeComparisonSource,
                            )}
                            {#if activeSource && activeSource.cues}
                                {#each activeSource.cues.slice(1) as cue, index}
                                    <div
                                            class="existing-timeline-tick {isChapterAligned(
                      cue.timestamp,
                      currentOption.timestamps,
                    )
                      ? 'aligned'
                      : ''}"
                                            style="left: {(cue.timestamp / bookDuration) * 100}%"
                                    ></div>
                                {/each}
                            {/if}
                        {/if}

                        <!-- Selected chapters ticks -->
                        <div class="timeline-ticks">
                            {#each currentOption.timestamps as timestamp, index}
                                {@const activeSource = activeComparisonSource
                                    ? existingCueSources.find(
                                        (source) => source.id === activeComparisonSource,
                                    )
                                    : null}
                                {@const existingTimestamps = activeSource
                                    ? activeSource.cues.map((c) => c.timestamp)
                                    : []}
                                <div
                                        class="timeline-tick {isComparing
                    ? 'compared'
                    : ''} {isChapterAligned(timestamp, existingTimestamps)
                    ? 'aligned'
                    : ''}"
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

                        <!-- Alignment percentage display between the labels -->
                        {#if activeComparisonSource}
                            {@const activeSource = existingCueSources.find(
                                (source) => source.id === activeComparisonSource,
                            )}
                            {#if activeSource && activeSource.cues}
                                {@const existingTimestamps = activeSource.cues.map(
                                    (c) => c.timestamp,
                                )}
                                {@const alignmentPercentage = calculateAlignmentPercentage(
                                    existingTimestamps,
                                    currentOption.timestamps,
                                )}
                                <span
                                        class="alignment-text"
                                        style="color: {getAlignmentColor(alignmentPercentage)}"
                                >
                  {#if innerWidth > 480}
                    Alignment with {activeSource.name}: {alignmentPercentage}%
                  {:else}
                    Alignment: {alignmentPercentage}%
                  {/if}
                </span>
                            {/if}
                        {/if}

                        <span class="timeline-end">{formatTimelineTime(bookDuration)}</span>
                    </div>
                </div>
            </div>
        {/if}

        <div class="slider-container">
            <div
                    class="slider-wrapper"
                    role="slider"
                    tabindex="0"
                    aria-valuemin="0"
                    aria-valuemax={cueSets.length - 1}
                    aria-valuenow={sliderValue}
                    aria-valuetext={currentOption
          ? `${currentOption.chapter_count} chapters`
          : "No selection"}
                    aria-label="Chapter count selector"
                    on:mousedown={handleTrackMouseDown}
                    on:touchstart={handleTrackTouchStart}
                    on:keydown={handleKeyDown}
                    bind:this={trackElement}
            >
                <div class="chapter-track">
                    <div class="track-line"></div>
                </div>
                <div class="slider-stops">
                    {#each cueSets as option, index (option.chapter_count)}
                        <button
                                class="slider-stop"
                                class:active={sliderValue === index}
                                style="left: {getProportionalPosition(option.chapter_count)}%"
                                on:click={() => handleStopClick(index)}
                                disabled={loading}
                                aria-label="Select cue set {index +
                1} with {option.chapter_count} chapters"
                        >
                            <div class="stop-marker"></div>
                        </button>
                    {/each}

                    <!-- Selected option bubble above slider -->
                    {#if currentOption}
                        <div
                                class="selected-bubble"
                                style="left: {getProportionalPosition(
                currentOption.chapter_count,
              )}%"
                        >
                            <div class="bubble-content">
                                <div class="bubble-set-label">
                                    Set {cueSets.findIndex(
                                    (opt) => opt.chapter_count === currentOption.chapter_count,
                                ) + 1}
                                </div>
                                <div class="bubble-main">
                  <span class="bubble-number"
                  >{currentOption.chapter_count}</span
                  >
                                    <span class="bubble-cues-label">Cues</span>
                                </div>
                            </div>
                            <div class="bubble-tail"></div>
                        </div>
                    {/if}
                </div>
            </div>

            <div class="usage-hint">← Click or drag to select a cue set →</div>
        </div>

        <!-- Include Unaligned Timestamps Options -->
        {#if currentOption && existingCueSources.length > 0}
            {@const hasUnalignedOptions = existingCueSources.some((source) => {
                const unalignedCount = source.cues.filter(
                    (cue) =>
                        !currentOption.timestamps.some(
                            (selected) => Math.abs(cue.timestamp - selected) <= 5,
                        ),
                ).length;
                return unalignedCount > 0;
            })}

            {#if hasUnalignedOptions}
                <div class="unaligned-options">
                    {#each existingCueSources as source}
                        {@const unalignedCount = source.cues.filter(
                            (cue) =>
                                !currentOption.timestamps.some(
                                    (selected) => Math.abs(cue.timestamp - selected) <= 5,
                                ),
                        ).length}

                        {#if unalignedCount > 0}
                            <label class="checkbox-option">
                                <input
                                        type="checkbox"
                                        bind:checked={includeUnalignedSources[source.id]}
                                        disabled={loading}
                                />
                                Include {unalignedCount} unaligned cues from {source.name}
                            </label>
                        {/if}
                    {/each}
                </div>
            {/if}
        {/if}

        <div class="actions">
            <button
                    class="btn btn-verify"
                    on:click={proceedWithSelection}
                    disabled={!selectedOption || loading}
            >
                {#if loading}
                    <span class="btn-spinner"></span>
                    Processing...
                {:else if hasAdditionalTimestamps}
                    Create {selectedOption + getAdditionalTimestampCount()} Chapters
                {:else}
                    Create {selectedOption} Chapters
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
        margin-bottom: 3rem;
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

    .timeline-visualization {
        background: var(--bg-secondary);
        border: 1px solid var(--border-color);
        border-radius: 8px;
        padding: 1.5rem 1.5rem 0.75rem 1.5rem;
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
        transition: top 0.2s ease,
        height 0.2s ease,
        background 0.2s ease,
        transform 0.2s ease;
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

    .slider-container {
        margin-bottom: 2.5rem;
    }

    .slider-wrapper {
        position: relative;
        margin: 2rem 2rem;
        padding: 2rem 0;
        cursor: pointer;
        user-select: none;
    }

    .chapter-track {
        position: relative;
        width: 100%;
        height: 8px;
        margin: 2rem 0;
    }

    .track-line {
        width: 100%;
        height: 8px;
        border-radius: 4px;
        background: var(--bg-tertiary);
    }

    .slider-stops {
        position: absolute;
        top: 50%;
        left: 0;
        right: 0;
        height: 0;
        pointer-events: none;
    }

    .slider-stop {
        position: absolute;
        top: 50%;
        transform: translate(-50%, -50%);
        display: flex;
        flex-direction: column;
        align-items: center;
        background: none;
        border: none;
        cursor: pointer;
        padding: 0.5rem;
        margin: 0;
    }

    .slider-stop:disabled {
        cursor: not-allowed;
        opacity: 0.6;
    }

    .stop-marker {
        width: 8px;
        height: 8px;
        border-radius: 50%;
        background: var(--border-color);
        border: 1px solid var(--slider-stop-outline);
        transition: all 0.2s ease;
    }

    .slider-stop:hover:not(:disabled) .stop-marker {
        transform: scale(1.2);
    }

    .slider-stop.active .stop-marker {
        background: var(--primary-color);
        transform: scale(1.4);
    }

    .selected-bubble {
        position: absolute;
        top: -4.5rem;
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
        padding: 0.5rem 0.75rem;
        border-radius: 8px;
        font-size: 0.875rem;
        font-weight: 600;
        white-space: nowrap;
        position: relative;
        display: flex;
        flex-direction: column;
        align-items: center;
    }

    .bubble-set-label {
        font-size: 0.625rem;
        font-weight: 500;
        opacity: 0.8;
        text-transform: uppercase;
        line-height: 1.3;
    }

    .bubble-main {
        display: flex;
        line-height: 1.3;
        align-items: center;
        gap: 0.2rem;
    }

    .bubble-number {
        font-size: 1.125rem;
        font-weight: 700;
    }

    .bubble-cues-label {
        font-size: 0.75rem;
        font-weight: 500;
        opacity: 0.8;
    }

    .bubble-tail {
        width: 0;
        height: 0;
        border-left: 8px solid transparent;
        border-right: 8px solid transparent;
        border-top: 8px solid var(--primary-color);
        margin-top: -1px;
    }

    .usage-hint {
        text-align: center;
        font-size: 0.8rem;
        color: var(--text-secondary);
        z-index: -1;
        margin-top: -5rem;
        font-style: italic;
    }

    .actions {
        display: flex;
        justify-content: center;
    }

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
        0% {
            transform: rotate(0deg);
        }
        100% {
            transform: rotate(360deg);
        }
    }

    .float-right {
        float: right;
        margin-left: 1rem;
    }

    /* Responsive design */
    @media (max-width: 768px) {
        .chapter-selection {
            padding: 1rem;
        }

        .header h2 {
            font-size: 1.5rem;
        }

        .slider-wrapper {
            padding-top: 1.5rem;
        }

        .bubble-content {
            padding: 0.4rem 0.6rem;
            gap: 0.1rem;
        }

        .bubble-set-label {
            font-size: 0.5rem;
        }

        .bubble-number {
            font-size: 1rem;
        }

        .bubble-cues-label {
            font-size: 0.5rem;
        }

        .selected-bubble {
            top: -4rem;
        }

        .actions .btn {
            min-width: 200px;
            font-size: 1rem;
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
    }

    /* Usage Hints Styles */
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
        from {
            opacity: 0;
            transform: translateY(-10px);
        }
        to {
            opacity: 1;
            transform: translateY(0);
        }
    }

    /* Mobile responsive adjustments for usage hints */
    @media (max-width: 768px) {
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
    }

    /* Unaligned Options Styles */
    .unaligned-options {
        display: flex;
        align-items: center;
        flex-direction: column;
        gap: 0.75rem;
        margin-bottom: 2rem;
    }

    .checkbox-option {
        display: flex;
        align-items: center;
        gap: 0.5rem;
        cursor: pointer;
        font-size: 0.95rem;
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
    }

    .checkbox-option input[type="checkbox"]:disabled {
        cursor: not-allowed;
        opacity: 0.6;
    }

    .checkbox-option:has(input[type="checkbox"]:disabled) {
        cursor: not-allowed;
        opacity: 0.6;
    }

    /* Mobile responsive adjustments for unaligned options */
    @media (max-width: 768px) {
        .unaligned-options {
            margin-bottom: 1rem;
        }

        .checkbox-option {
            font-size: 0.9rem;
        }
    }

    /* Tooltip Styles */
    .tooltip-container {
        position: relative;
        display: inline-flex;
        align-items: center;
        cursor: help;
    }

    /* Override Icon component's built-in title to prevent "help" tooltip */
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

    /* Mini timeline for legend */
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

    /* Responsive tooltip */
    @media (max-width: 768px) {
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
    }

    @media (pointer: coarse) {
        .slider-wrapper {
            touch-action: manipulation;
            -webkit-tap-highlight-color: transparent;
        }
    }
</style>
