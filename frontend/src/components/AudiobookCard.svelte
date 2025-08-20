<script>
    import BookHeadphones from "@lucide/svelte/icons/book-headphones";

    export let title = "";
    export let duration = 0;
    export let coverImageUrl = null;
    export let showDuration = true;
    export let fileCount = 1;
    export let showFileCount = true;
    export let size = "normal"; // 'normal' or 'compact'

    // Format duration for display
    function formatDuration(seconds) {
        const hours = Math.floor(seconds / 3600);
        const minutes = Math.floor((seconds % 3600) / 60);
        const secs = Math.floor(seconds % 60);

        if (hours > 0) {
            return `${hours}h ${minutes}m ${secs}s`;
        }
        return `${minutes}m ${secs}s`;
    }
</script>

<div class="audiobook-card" class:compact={size === "compact"}>
    <div class="audiobook-icon">
        {#if coverImageUrl}
            <img src={coverImageUrl} alt="Audiobook cover" class="cover-image"/>
        {:else}
            <BookHeadphones size="40"/>
        {/if}
    </div>
    <div class="audiobook-details">
        <h3 class="audiobook-title">{title || "Audiobook"}</h3>
        <div class="audiobook-metadata">
            {#if showDuration && duration > 0}
                <div class="audiobook-duration">{formatDuration(duration)}</div>
            {/if}
            {#if showFileCount && fileCount > 1}
                <div class="audiobook-file-count">{fileCount} files</div>
            {/if}
        </div>
    </div>
    <slot name="actions"/>
</div>

<style>
    .audiobook-card {
        background: linear-gradient(
                135deg,
                color-mix(in srgb, var(--accent-1) 18%, transparent) 0%,
                color-mix(in srgb, var(--accent-2) 14%, transparent) 100%
        );
        border: 1px solid color-mix(in srgb, var(--accent-1) 35%, transparent);
        border-radius: 16px;
        padding: 1rem;
        display: flex;
        align-items: center;
        gap: 1.25rem;
        width: 100%;
    }

    .audiobook-card.compact {
        padding: 1rem;
        gap: 1rem;
    }

    .audiobook-icon {
        font-size: 2.5rem;
        flex-shrink: 0;
        position: relative;
        width: 80px;
        height: 80px;
        display: flex;
        align-items: center;
        justify-content: center;
    }

    .audiobook-card.compact .audiobook-icon {
        width: 60px;
        height: 60px;
        font-size: 2rem;
    }

    .cover-image {
        width: 100%;
        height: 100%;
        object-fit: cover;
        border-radius: 8px;
    }

    .audiobook-details {
        flex: 1;
        min-width: 0;
    }

    .audiobook-title {
        margin: 0 0 0.5rem 0;
        color: var(--text-primary);
        font-size: 1.4rem;
        font-weight: 600;
        line-height: 1.3;
        word-wrap: break-word;
    }

    .audiobook-card.compact .audiobook-title {
        font-size: 1rem;
        margin-bottom: 0.25rem;
    }

    .audiobook-metadata {
        display: flex;
        gap: 0.5rem;
        flex-wrap: wrap;
        align-items: center;
    }

    .audiobook-duration,
    .audiobook-file-count {
        padding: 0.25rem 0.5rem;
        border-radius: 100px;
        font-size: 0.75rem;
        color: var(--text-primary);
        font-weight: 500;
        display: inline-block;
        border: 1px solid rgba(255, 255, 255, 0.3);
    }

    .audiobook-file-count {
        background: color-mix(in srgb, var(--accent-1) 12%, transparent);
        border-color: color-mix(in srgb, var(--accent-1) 45%, transparent);
    }

    /* Responsive design */
    @media (max-width: 768px) {
        .audiobook-card {
            padding: 1rem;
            gap: 1rem;
        }

        .audiobook-title {
            font-size: 1.2rem;
        }
    }

    @media (max-width: 480px) {
        .audiobook-duration,
        .audiobook-file-count {
            font-size: 0.5rem;
        }
    }
</style>
