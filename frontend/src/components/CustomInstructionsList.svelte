<script>
    import {onMount} from "svelte";
    import {api} from "../utils/api.js";
    import { dndzone } from "svelte-dnd-action";
    
    // Icons
    import CircleQuestionMark from "@lucide/svelte/icons/circle-question-mark";
    import GripVertical from "@lucide/svelte/icons/grip-vertical";
    import Plus from "@lucide/svelte/icons/plus";
    import Trash2 from "@lucide/svelte/icons/trash-2";
    
    // State
    let instructions = $state([]);
    let loading = $state(true);
    let saveTimeout = null;
    let dragDisabled = false;
    
    onMount(async () => {
        await loadInstructions();
    });
    
    async function loadInstructions() {
        try {
            loading = true;
            const response = await api.batch.getCustomInstructions();
            instructions = response.instructions || [];
        } catch (error) {
            console.error('Failed to load custom instructions:', error);
            instructions = [];
        } finally {
            loading = false;
        }
    }
    
    function saveInstructionsDebounced() {
        if (saveTimeout) {
            clearTimeout(saveTimeout);
        }
        
        saveTimeout = setTimeout(async () => {
            try {
                await api.batch.saveCustomInstructions(instructions);
            } catch (error) {
                console.error('Failed to save custom instructions:', error);
            }
        }, 600);
    }
    
    async function saveInstructionsImmediate() {
        if (saveTimeout) {
            clearTimeout(saveTimeout);
            saveTimeout = null;
        }
        
        try {
            await api.batch.saveCustomInstructions(instructions);
        } catch (error) {
            console.error('Failed to save custom instructions:', error);
        }
    }
    
    async function addInstruction() {
        const newInstruction = {
            id: crypto.randomUUID(),
            text: "",
            checked: true,
            order: instructions.length
        };
        
        instructions = [...instructions, newInstruction];
        await saveInstructionsImmediate();
        
        setTimeout(() => {
            const newInput = document.querySelector(`input[data-id="${newInstruction.id}"]`);
            if (newInput) {
                newInput.focus();
            }
        }, 50);
    }
    
    async function deleteInstruction(id) {
        instructions = instructions.filter(inst => inst.id !== id);
        instructions = instructions.map((inst, index) => ({
            ...inst,
            order: index
        }));
        await saveInstructionsImmediate();
    }
    
    async function toggleChecked(id) {
        instructions = instructions.map(inst =>
            inst.id === id ? {...inst, checked: !inst.checked} : inst
        );
        await saveInstructionsImmediate();
    }
    
    function updateText(id, text) {
        instructions = instructions.map(inst => 
            inst.id === id ? {...inst, text} : inst
        );
        saveInstructionsDebounced();
    }
    
    function handleDndConsider(e) {
        instructions = e.detail.items;
    }
    
    async function handleDndFinalize(e) {
        instructions = e.detail.items.map((inst, index) => ({
            ...inst,
            order: index
        }));
        await saveInstructionsImmediate();
    }
    
    function handleKeydown(event, id) {
        if (event.key === 'Enter') {
            event.preventDefault();
            addInstruction();
        }
    }
</script>

<div class="custom-instructions">
    <div class="instructions-header">
        <h4>
            Custom Instructions
            <div
                class="help-icon"
                data-tooltip="A persisted library of instructions that can be reused across audiobooks. Check the items you wish to enable for this cleanup."
            >
                <CircleQuestionMark size="14" />
            </div>
        </h4>
    </div>
    
    {#if loading}
        <div class="loading">Loading instructions...</div>
    {:else}
        <div
            class="instructions-list"
            use:dndzone={{
                items: instructions,
                dragDisabled,
                dropTargetStyle: {
                    outline: "2px solid var(--ai-accent)",
                    outlineOffset: "2px"
                }
            }}
            onconsider={handleDndConsider}
            onfinalize={handleDndFinalize}
        >
            {#each instructions as instruction (instruction.id)}
                <div class="instruction-wrapper" data-id={instruction.id}>
                    <label class="checkbox-container">
                        <input
                            type="checkbox"
                            checked={instruction.checked}
                            onchange={() => toggleChecked(instruction.id)}
                        />
                        <span class="checkmark"></span>
                    </label>
                    
                    <div class="instruction-item">
                        <div class="text-input-container">
                            <input
                                type="text"
                                bind:value={instruction.text}
                                oninput={(e) => updateText(instruction.id, e.target.value)}
                                onkeydown={(e) => handleKeydown(e, instruction.id)}
                                data-id={instruction.id}
                                placeholder="Enter instruction..."
                            />
                        </div>
                        
                        <button
                            class="delete-btn"
                            onclick={() => deleteInstruction(instruction.id)}
                            title="Delete instruction"
                            type="button"
                        >
                            <Trash2 size="16" />
                        </button>
                        <div class="drag-handle" title="Drag to reorder">
                            <GripVertical size="16" />
                        </div>
                    </div>
                </div>
            {/each}
        </div>
        
        <button 
            class="add-btn"
            onclick={addInstruction}
            type="button"
        >
            <Plus size="16" />
            Add Instruction
        </button>
    {/if}
</div>

<style>
    .custom-instructions {
        display: flex;
        flex-direction: column;
        height: 100%;
        min-height: 200px;
    }
    
    .instructions-header h4 {
        margin: 0 0 0.5rem 0;
        color: var(--text-primary);
        display: flex;
        align-items: center;
        gap: 0.5rem;
    }
    
    .loading {
        display: flex;
        align-items: center;
        justify-content: center;
        padding: 2rem;
        color: var(--text-muted);
        font-size: 0.875rem;
    }
    
    .instructions-list {
        flex: 1;
        margin-bottom: 0.25rem;
        display: flex;
        flex-direction: column;
        min-height: 0;
    }
    
    .instruction-wrapper {
        display: flex;
        align-items: center;
        gap: 0.5rem;
        margin-bottom: 1px;
    }
    
    .instruction-item {
        display: flex;
        align-items: center;
        gap: 0.25rem;
        padding: 0.25rem 0.25rem 0.25rem 0.25rem;
        background: var(--bg-secondary);
        border: 1px solid var(--border-color);
        border-radius: 0.375rem;
        position: relative;
        flex: 1;
    }
    
    .instruction-item:hover {
        border-color: var(--ai-accent);
    }
    
    .drag-handle {
        color: var(--text-muted);
        cursor: grab;
        display: flex;
        align-items: center;
        padding: 0.25rem 0;
        
    }
    
    .drag-handle:hover {
        color: var(--text-secondary);
    }
    
    .drag-handle:active {
        cursor: grabbing;
    }
    
    .checkbox-container {
        position: relative;
        display: flex;
        align-items: center;
        cursor: pointer;
        flex-shrink: 0;
    }
    
    .checkbox-container input {
        opacity: 0;
        width: 0;
        height: 0;
        margin: 0;
    }
    
    .checkmark {
        width: 16px;
        height: 16px;
        border: 1px solid var(--border-color);
        border-radius: 3px;
        background: var(--bg-primary);
        transition: all 0.2s ease;
        position: relative;
    }
    
    .checkbox-container:hover .checkmark {
        border-color: var(--ai-accent);
    }
    
    .checkbox-container input:checked + .checkmark {
        background: var(--ai-accent);
        border-color: var(--ai-accent);
    }
    
    .checkbox-container input:checked + .checkmark::after {
        content: '';
        position: absolute;
        left: 5px;
        top: 2px;
        width: 4px;
        height: 8px;
        border: solid white;
        border-width: 0 2px 2px 0;
        transform: rotate(45deg);
    }
    
    .text-input-container {
        flex: 1;
        position: relative;
    }
    
    .text-input-container input {
        width: 100%;
        padding: 0.5rem;
        border: 1px solid transparent;
        border-radius: 0.25rem;
        background: var(--bg-primary);
        color: var(--text-primary);
        font-size: 0.875rem;
        transition: border-color 0.2s ease;
    }
    
    .text-input-container input:focus {
        outline: none;
        border-color: var(--ai-accent);
    }
    
    .text-input-container input::placeholder {
        color: var(--text-muted);
    }
    
    
    .delete-btn {
        padding: 0.25rem;
        border: none;
        background: transparent;
        color: var(--text-muted);
        cursor: pointer;
        border-radius: 0.25rem;
        transition: all 0.2s ease;
        display: flex;
        align-items: center;
        justify-content: center;
    }
    
    .delete-btn:hover {
        background: rgba(239, 68, 68, 0.1);
        color: #ef4444;
    }
    
    .add-btn {
        display: flex;
        align-items: center;
        justify-content: center;
        gap: 0.5rem;
        padding: 0.35rem;
        border: 1px dashed var(--border-color);
        background: transparent;
        color: var(--text-muted);
        border-radius: 0.375rem;
        cursor: pointer;
        font-size: 0.875rem;
        transition: all 0.2s ease;
        margin-left: 1.5rem;
    }
    
    .add-btn:hover {
        border-color: var(--ai-accent);
        color: var(--ai-accent);
        background: color-mix(in srgb, var(--ai-accent) 5%, transparent);
    }
    
    .instruction-wrapper {
        touch-action: none;
    }
    
    :global(.dnd-action-dragged-el) {
        opacity: 0.5;
        transform: rotate(5deg);
        box-shadow: 0 8px 16px rgba(0, 0, 0, 0.15);
    }
    
    :global(.dnd-action-dragged-el .drag-handle) {
        cursor: grabbing;
    }
    
    .help-icon {
        border: none;
        display: inline-flex;
        background: transparent;
        color: var(--text-secondary);
        position: relative;
        cursor: help;
        padding: 2px;
        border-radius: 50%;
        transition: all 0.2s ease;
    }
    
    .help-icon:hover {
        color: var(--primary-color);
        background: var(--bg-tertiary);
    }
    
    .help-icon[data-tooltip]:hover::after {
        content: attr(data-tooltip);
        position: fixed;
        transform: translate(-50%, calc(-100% - 8px));
        padding: 8px 12px;
        background: var(--bg-primary);
        color: var(--text-primary);
        border: 1px solid var(--border-color);
        border-radius: 6px;
        font-size: 0.875rem;
        line-height: 1.4;
        white-space: pre-line;
        max-width: 360px;
        z-index: 10001;
        font-weight: normal;
    }
    
    .help-icon[data-tooltip]:hover::before {
        content: "";
        position: absolute;
        bottom: 100%;
        left: 50%;
        transform: translateX(-50%);
        margin-bottom: -5px;
        border: 6px solid transparent;
        border-top-color: var(--border-color);
        z-index: 10002;
    }
</style>