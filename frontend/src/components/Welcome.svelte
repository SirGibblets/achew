<script>
    import {createEventDispatcher} from "svelte";
    import DocLink from "./DocLink.svelte";
    import Icon from "./Icon.svelte";
    import ArrowRight from "@lucide/svelte/icons/arrow-right";

    const dispatch = createEventDispatcher();

    let loading = false;

    async function handleGetStarted() {
        if (loading) return;
        loading = true;
        try {
            const response = await fetch("/api/complete-welcome", {method: "POST"});
            if (response.ok) {
                dispatch("welcome-dismissed");
            } else {
                console.error("Failed to dismiss welcome screen");
            }
        } catch (error) {
            console.error("Error dismissing welcome screen:", error);
        } finally {
            loading = false;
        }
    }
</script>

<div class="welcome-container">
    <div class="welcome-header">
        <div class="header-icon">
            <Icon name="achew-logo" size={96} color="var(--primary)"/>
        </div>
        <h1>Welcome to Achew</h1>
        <p class="tagline">The Audiobook Chapter Extraction Wizard</p>
    </div>

    <p class="intro">
        To get started, you'll need to connect Achew to your Audiobookshelf server. You can
        then optionally configure an LLM provider for AI-powered cleanup.
    </p>

    <div class="welcome-actions">
        <button class="btn btn-verify" on:click={handleGetStarted} disabled={loading}>
            Get Started
            <ArrowRight size="18"/>
        </button>
    </div>

    <div class="welcome-docs">
        <DocLink path="/getting-started/achew-basics/" text="Read the docs" inlineIcon />
    </div>
</div>

<style>
    .welcome-container {
        max-width: 700px;
        margin: 0 auto;
        flex: 1;
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
        text-align: center;
        padding-bottom: 8rem;
    }

    .welcome-header {
        margin-bottom: 2rem;
    }

    .header-icon {
        margin-bottom: 1.25rem;
        display: flex;
        justify-content: center;
    }

    .welcome-header h1 {
        margin: 0;
        color: var(--text-primary);
        font-size: 2.25rem;
        font-weight: 700;
    }

    .tagline {
        margin: 0;
        color: var(--text-secondary);
        font-size: 1.05rem;
        font-weight: 500;
    }

    .intro {
        margin: 0rem 0 2.5rem 0;
        line-height: 1.6;
        max-width: 560px;
        font-size: 0.9rem;
        padding: 1rem 1.25rem;
        border: 1px solid var(--border-color);
        border-radius: 12px;
    }

    .welcome-actions {
        display: flex;
        justify-content: center;
    }

    .welcome-docs {
        margin-top: 1.25rem;
        font-size: 0.85rem;
    }

    @media (max-width: 768px) {
        .welcome-container {
            margin: 1rem;
        }

        .welcome-header h1 {
            font-size: 1.75rem;
        }

        .tagline {
            font-size: 0.95rem;
        }
    }
</style>
