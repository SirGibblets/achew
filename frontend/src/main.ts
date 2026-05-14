import { mount } from 'svelte';
import App from './App.svelte';
import './styles/global.css';

const target = document.getElementById('app');
if (!target) {
  throw new Error('Could not find #app target element');
}

const app = mount(App, { target });

export default app;
