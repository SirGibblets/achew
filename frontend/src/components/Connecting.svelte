<script>
    import {isConnected, websocket as ws} from "../stores/websocket.js";
    import Icon from "./Icon.svelte";

    export let message = null;

    $: statusText =
        message ?? ($ws.reconnecting ? "Reconnecting…" : "Connecting...");
</script>

<div class="connecting">
    <div class="stack">
        <div class="logo-spinner">
            <div class="spinner-ring" aria-hidden="true"></div>
            <div class="logo">
                <Icon
                        name="achew-logo"
                        size="64"
                        color="linear-gradient(135deg, var(--accent-gradient-start) 0%, var(--accent-gradient-end) 100%)"
                />
            </div>
        </div>
        <p class="status">{statusText}</p>
    </div>
</div>

<style>
    .connecting {
        display: flex;
        align-items: center;
        justify-content: center;
        flex: 1;
        min-height: 60vh;
    }

    .stack {
        display: flex;
        flex-direction: column;
        align-items: center;
        gap: 2rem;
        width: 100%;
    }

    .logo-spinner {
        position: relative;
        width: 96px;
        height: 96px;
        display: grid;
        place-items: center;
    }

    .spinner-ring {
        position: absolute;
        width: 96px;
        height: 96px;
        border-radius: 50%;
        border: 2px solid transparent;
        border-top-color: var(--primary);
        border-right-color: color-mix(in srgb, var(--primary) 60%, transparent);
        animation: spin 1.2s linear infinite;
    }

    .logo {
        z-index: 1;
        margin-left: 6px;
    }

    @keyframes spin {
        to {
            transform: rotate(360deg);
        }
    }

    .status {
        margin: 0.5rem 0 0;
        color: var(--text-primary);
        font-weight: 500;
    }
</style>
