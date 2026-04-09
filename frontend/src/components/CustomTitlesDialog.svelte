<script>
    import {session} from "../stores/session.js";
    import {api, handleApiError} from "../utils/api.js";

    import X from "@lucide/svelte/icons/x";

    let {
        isOpen = $bindable(false),
        sourceId = '',
    } = $props();

    let textarea = $state('');
    let saving = $state(false);
    let error = $state(null);

    /* Pre-populate textarea from the current source titles when dialog opens. */
    $effect(() => {
        if (isOpen && sourceId) {
            const src = ($session.titleSources || []).find(s => s.id === sourceId);
            textarea = src ? (src.titles || []).join('\n') : '';
            error = null;
        }
        if (!isOpen) {
            textarea = '';
            error = null;
        }
    });

    /* Scroll lock */
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

    async function handleSave() {
        saving = true;
        error = null;
        try {
            const titles = textarea.split('\n').map(l => l.trim()).filter(Boolean);
            await api.sources.updateTitles(sourceId, titles);
            isOpen = false;
        } catch (err) {
            error = handleApiError(err);
        } finally {
            saving = false;
        }
    }

    function handleCancel() {
        isOpen = false;
    }

    function handleKeydown(e) {
        if (e.key === 'Escape' && !saving) isOpen = false;
    }
</script>

{#if isOpen}
    <div class="backdrop" onclick={handleCancel} role="presentation">
        <div
            class="dialog"
            role="dialog"
            aria-modal="true"
            aria-label="Edit Custom Titles"
            tabindex="-1"
            onclick={(e) => e.stopPropagation()}
            onkeydown={handleKeydown}
        >
            <div class="modal-header">
                <div class="modal-header-text">
                    <h3>Edit Custom Titles</h3>
                    <p class="description">
                        Enter one chapter title per line.
                    </p>
                </div>
                <button class="close-btn" onclick={handleCancel} disabled={saving} aria-label="Close">
                    <X size="20"/>
                </button>
            </div>

            <div class="modal-body">
                <textarea
                    class="title-input"
                    bind:value={textarea}
                    placeholder={"Chapter 1\nChapter 2\n…"}
                    disabled={saving}
                    rows="16"
                    spellcheck="false"
                ></textarea>

                {#if error}
                    <div class="error-msg">{error}</div>
                {/if}
            </div>

            <div class="modal-footer">
                <button class="btn secondary" onclick={handleCancel} disabled={saving}>
                    Cancel
                </button>
                <button class="btn primary" onclick={handleSave} disabled={saving}>
                    {#if saving}Saving…{:else}Save{/if}
                </button>
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
        z-index: 1000;
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
        max-width: 540px;
        max-height: 88vh;
        display: flex;
        flex-direction: column;
        overflow: hidden;
    }

    .modal-header {
        display: flex;
        align-items: flex-start;
        justify-content: space-between;
        padding: 1.25rem 1.5rem;
        border-bottom: 1px solid var(--border-color);
        flex-shrink: 0;
        gap: 1rem;
    }

    .modal-header-text {
        display: flex;
        flex-direction: column;
        gap: 0.25rem;
    }

    .modal-header h3 {
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

    .close-btn:hover:not(:disabled) { background: var(--bg-tertiary); color: var(--text-primary); }
    .close-btn:disabled { opacity: 0.4; cursor: default; }

    .modal-body {
        flex: 1;
        overflow-y: auto;
        padding: 1.25rem 1.5rem;
        display: flex;
        flex-direction: column;
        gap: 0.875rem;
    }

    .description {
        margin: 0;
        font-size: 0.875rem;
        color: var(--text-secondary);
        line-height: 1.5;
    }

    .title-input {
        width: 100%;
        box-sizing: border-box;
        resize: vertical;
        padding: 0.75rem;
        border: 1px solid var(--border-color);
        border-radius: 8px;
        background: var(--bg-secondary);
        color: var(--text-primary);
        font-size: 0.875rem;
        font-family: inherit;
        line-height: 1.6;
        min-height: 200px;
    }

    .title-input:focus { outline: none; border-color: var(--primary-color); }
    .title-input:disabled { opacity: 0.6; }

    .error-msg {
        padding: 0.625rem 0.875rem;
        border-radius: 6px;
        background: color-mix(in srgb, var(--error-color, #e53e3e) 10%, transparent);
        border: 1px solid color-mix(in srgb, var(--error-color, #e53e3e) 30%, transparent);
        font-size: 0.875rem;
        color: var(--text-primary);
    }

    .modal-footer {
        display: flex;
        justify-content: flex-end;
        gap: 0.75rem;
        padding: 1rem 1.5rem;
        border-top: 1px solid var(--border-color);
        flex-shrink: 0;
    }

    .btn {
        padding: 0.5rem 1.25rem;
        border-radius: 7px;
        font-size: 0.875rem;
        cursor: pointer;
        border: 1px solid transparent;
        transition: opacity 0.15s, background 0.15s;
    }

    .btn:disabled { opacity: 0.5; cursor: default; }

    .btn.primary {
        background: var(--primary-color);
        color: #fff;
    }

    .btn.primary:not(:disabled):hover { opacity: 0.88; }

    .btn.secondary {
        background: var(--bg-secondary);
        border-color: var(--border-color);
        color: var(--text-primary);
    }

    .btn.secondary:not(:disabled):hover { background: var(--bg-tertiary); }
</style>
