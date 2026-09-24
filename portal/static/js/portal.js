/**
 * Kindle Tasks Pro Portal - Interactive Engine
 * Handles Drag & Drop, AJAX updates, Stage transitions, Crons triggers, and Gemini AI analysis
 */

// Toast Notifications Helper
function showToast(message, type = 'success') {
  let container = document.querySelector('.toast-container');
  if (!container) {
    container = document.createElement('div');
    container.className = 'toast-container';
    document.body.appendChild(container);
  }

  const toast = document.createElement('div');
  toast.className = `toast toast-${type}`;
  toast.innerHTML = `
    <span>${type === 'success' ? '✓' : '⚠'}</span>
    <div>${message}</div>
  `;
  container.appendChild(toast);

  setTimeout(() => {
    toast.style.opacity = '0';
    toast.style.transform = 'translateY(10px)';
    toast.style.transition = 'all 0.3s ease';
    setTimeout(() => toast.remove(), 300);
  }, 4000);
}

// Modal Helpers
function openModal(id) {
  const modal = document.getElementById(id);
  if (modal) {
    modal.classList.add('active');
  }
}

function closeModal(id) {
  const modal = document.getElementById(id);
  if (modal) {
    modal.classList.remove('active');
  }
}

// Drag & Drop for Kanban Cards
let draggedCard = null;

function initKanbanDragAndDrop() {
  const cards = document.querySelectorAll('.task-card');
  const columns = document.querySelectorAll('.column-cards');

  cards.forEach(card => {
    card.addEventListener('dragstart', (e) => {
      draggedCard = card;
      card.classList.add('dragging');
      e.dataTransfer.setData('text/plain', card.dataset.taskId);
    });

    card.addEventListener('dragend', () => {
      card.classList.remove('dragging');
      draggedCard = null;
      document.querySelectorAll('.kanban-column').forEach(col => col.classList.remove('drag-over'));
    });
  });

  columns.forEach(column => {
    const parentCol = column.closest('.kanban-column');

    column.addEventListener('dragover', (e) => {
      e.preventDefault();
      if (parentCol) parentCol.classList.add('drag-over');
    });

    column.addEventListener('dragleave', () => {
      if (parentCol) parentCol.classList.remove('drag-over');
    });

    column.addEventListener('drop', async (e) => {
      e.preventDefault();
      if (parentCol) parentCol.classList.remove('drag-over');
      if (!draggedCard) return;

      const targetStage = column.dataset.stage;
      const taskId = draggedCard.dataset.taskId;
      const taskScope = draggedCard.dataset.taskScope;

      if (draggedCard.dataset.currentStage === targetStage) return;

      // Optimistic UI move
      column.appendChild(draggedCard);
      draggedCard.dataset.currentStage = targetStage;

      // Update select inside card if present
      const sel = draggedCard.querySelector('.quick-move-select');
      if (sel) sel.value = targetStage;

      try {
        const res = await fetch('/api/tasks/move', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            task_id: taskId,
            target_stage: targetStage,
            scope: taskScope
          })
        });
        const data = await res.json();
        if (res.ok) {
          showToast(`Tarea movida a ${targetStage.replace('_', ' ').toUpperCase()}`);
          updateColumnCounts();
        } else {
          showToast(data.detail || 'Error al mover tarea', 'error');
          setTimeout(() => location.reload(), 800);
        }
      } catch (err) {
        showToast('Error de red al mover tarea', 'error');
      }
    });
  });
}

// Quick Stage Select Change
async function handleQuickStageChange(selectElem) {
  const card = selectElem.closest('.task-card');
  const taskId = card.dataset.taskId;
  const taskScope = card.dataset.taskScope;
  const targetStage = selectElem.value;

  try {
    const res = await fetch('/api/tasks/move', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        task_id: taskId,
        target_stage: targetStage,
        scope: taskScope
      })
    });
    if (res.ok) {
      showToast('Etapa actualizada');
      const targetColumn = document.querySelector(`.column-cards[data-stage="${targetStage}"]`);
      if (targetColumn) {
        targetColumn.appendChild(card);
        card.dataset.currentStage = targetStage;
        updateColumnCounts();
      }
    } else {
      const err = await res.json();
      showToast(err.detail || 'Error al cambiar etapa', 'error');
    }
  } catch (err) {
    showToast('Error de conexión', 'error');
  }
}

// Recalculate Column Counts
function updateColumnCounts() {
  document.querySelectorAll('.kanban-column').forEach(col => {
    const stage = col.dataset.stage;
    const cards = col.querySelectorAll('.task-card');
    const badge = col.querySelector('.column-badge');
    if (badge) badge.textContent = cards.length;

    let totalSp = 0;
    cards.forEach(c => {
      const sp = parseFloat(c.dataset.storyPoints || 0);
      if (!isNaN(sp)) totalSp += sp;
    });
    const spBadge = col.querySelector('.column-sp-badge');
    if (spBadge) spBadge.textContent = `${totalSp.toFixed(1)} SP`;
  });
}

// Toggle Subtask
async function toggleSubtask(taskId, scope, index, checkbox) {
  try {
    const res = await fetch('/api/tasks/toggle-subtask', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        task_id: taskId,
        scope: scope,
        subtask_index: index
      })
    });
    if (res.ok) {
      const item = checkbox.closest('.checklist-item');
      if (item) item.classList.toggle('done', checkbox.checked);
      showToast('Subtarea actualizada');
    }
  } catch (err) {
    showToast('Error al actualizar subtarea', 'error');
  }
}

// Task Creation Form
async function submitCreateTask(event) {
  event.preventDefault();
  const form = event.target;
  const formData = new FormData(form);

  const payload = {
    title: formData.get('title'),
    description: formData.get('description') || '',
    priority: formData.get('priority') || 'Media',
    stage: formData.get('stage') || 'todo',
    scope: formData.get('scope') || 'fidel',
    story_points: formData.get('story_points') ? parseFloat(formData.get('story_points')) : null,
    estimated_hours: formData.get('estimated_hours') ? parseFloat(formData.get('estimated_hours')) : null,
    target_date: formData.get('target_date') || null
  };

  try {
    const res = await fetch('/api/tasks/create', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    if (res.ok) {
      showToast('Tarea creada exitosamente');
      closeModal('modal-create-task');
      setTimeout(() => location.reload(), 400);
    } else {
      const err = await res.json();
      showToast(err.detail || 'Error al crear tarea', 'error');
    }
  } catch (err) {
    showToast('Error de red al guardar tarea', 'error');
  }
}

// Task Delete
async function deleteTask(taskId, scope) {
  if (!confirm('¿Estás seguro de que deseas eliminar esta tarea definitivamente?')) return;

  try {
    const res = await fetch('/api/tasks/delete', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ task_id: taskId, scope: scope })
    });
    if (res.ok) {
      showToast('Tarea eliminada');
      const card = document.querySelector(`.task-card[data-task-id="${taskId}"]`);
      if (card) card.remove();
      updateColumnCounts();
      closeModal('modal-task-detail');
    } else {
      showToast('No se pudo eliminar la tarea', 'error');
    }
  } catch (err) {
    showToast('Error de conexión', 'error');
  }
}

// Task Details Modal Populate
function openTaskDetailModal(taskJson) {
  const task = typeof taskJson === 'string' ? JSON.parse(taskJson) : taskJson;

  document.getElementById('detail-task-id').value = task.id;
  document.getElementById('detail-scope').value = task.scope || 'fidel';
  document.getElementById('detail-title').value = task.title || '';
  document.getElementById('detail-description').value = task.description || '';
  document.getElementById('detail-stage').value = task.stage || 'todo';
  document.getElementById('detail-priority').value = task.priority || 'Media';
  document.getElementById('detail-sp').value = task.story_points || '';
  document.getElementById('detail-hours').value = task.estimated_hours || '';
  document.getElementById('detail-date').value = task.target_date || '';

  // Render subtasks
  const subtasksList = document.getElementById('detail-subtasks-list');
  if (subtasksList) {
    subtasksList.innerHTML = '';
    const subtasks = task.subtasks || [];
    if (subtasks.length === 0) {
      subtasksList.innerHTML = '<span style="color:var(--text-muted); font-size:0.8rem;">Sin subtareas</span>';
    } else {
      subtasks.forEach((st, idx) => {
        const isDone = typeof st === 'object' ? st.done : false;
        const text = typeof st === 'object' ? st.title : st;
        const div = document.createElement('div');
        div.className = `checklist-item ${isDone ? 'done' : ''}`;
        div.innerHTML = `
          <input type="checkbox" ${isDone ? 'checked' : ''} onchange="toggleSubtask('${task.id}', '${task.scope}', ${idx}, this)">
          <span>${text}</span>
        `;
        subtasksList.appendChild(div);
      });
    }
  }

  openModal('modal-task-detail');
}

// Submit Task Detail Updates
async function submitUpdateTask(event) {
  event.preventDefault();
  const form = event.target;
  const formData = new FormData(form);

  const payload = {
    task_id: formData.get('task_id'),
    scope: formData.get('scope'),
    title: formData.get('title'),
    description: formData.get('description'),
    stage: formData.get('stage'),
    priority: formData.get('priority'),
    story_points: formData.get('story_points') ? parseFloat(formData.get('story_points')) : null,
    estimated_hours: formData.get('estimated_hours') ? parseFloat(formData.get('estimated_hours')) : null,
    target_date: formData.get('target_date') || null
  };

  try {
    const res = await fetch('/api/tasks/update', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    if (res.ok) {
      showToast('Tarea actualizada');
      closeModal('modal-task-detail');
      setTimeout(() => location.reload(), 400);
    } else {
      showToast('Error al actualizar tarea', 'error');
    }
  } catch (err) {
    showToast('Error de conexión', 'error');
  }
}

// Recurrent Tasks Engine Trigger
async function triggerCronsNow() {
  const btn = document.getElementById('btn-run-crons');
  if (btn) {
    btn.disabled = true;
    btn.innerHTML = '⚡ Evaluando crones...';
  }

  try {
    const res = await fetch('/api/recurrent/run-now', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' }
    });
    const data = await res.json();
    if (res.ok && data.status === 'ok') {
      const summary = data.result;
      const msg = `Crones ejecutados: ${summary.generated_count} creadas, ${summary.skipped_count} omitidas (deduplicadas)`;
      showToast(msg, 'success');
      
      // If modal or log exists, show detailed alert
      alert(`Resultado del Motor de Crones:\n\n• Fecha: ${summary.date}\n• Reglas evaluadas: ${summary.evaluated_rules}\n• Tareas generadas: ${summary.generated_count}\n• Omitidas por duplicación: ${summary.skipped_count}\n\n${summary.skipped.map(s => ` - Omitida "${s.title}": ${s.reason}`).join('\n')}`);
      setTimeout(() => location.reload(), 600);
    } else {
      showToast('Error al ejecutar motor de crones', 'error');
    }
  } catch (err) {
    showToast('Error de conexión con el motor de crones', 'error');
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.innerHTML = '⚡ Ejecutar Crones';
    }
  }
}

// Recurrent Rule Toggle
async function toggleRule(ruleId) {
  try {
    const res = await fetch(`/api/recurrent/rules/${ruleId}/toggle`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' }
    });
    if (res.ok) {
      showToast('Estado de regla actualizado');
    } else {
      showToast('No se pudo actualizar la regla', 'error');
    }
  } catch (err) {
    showToast('Error de conexión', 'error');
  }
}

// Recurrent Rule Delete
async function deleteRule(ruleId) {
  if (!confirm('¿Eliminar esta regla de recurrencia definitivamente?')) return;
  try {
    const res = await fetch(`/api/recurrent/rules/${ruleId}/delete`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' }
    });
    if (res.ok) {
      showToast('Regla eliminada');
      const card = document.getElementById(`rule-card-${ruleId}`);
      if (card) card.remove();
    }
  } catch (err) {
    showToast('Error de conexión', 'error');
  }
}

// Recurrent Rule Add Submit
async function submitCreateRule(event) {
  event.preventDefault();
  const form = event.target;
  const formData = new FormData(form);

  const freq = formData.get('frequency');
  let daysOfWeek = [0, 1, 2, 3, 4, 5, 6];
  if (freq === 'weekdays') {
    daysOfWeek = [0, 1, 2, 3, 4];
  } else if (freq === 'custom_days') {
    daysOfWeek = Array.from(form.querySelectorAll('input[name="custom_day"]:checked')).map(cb => parseInt(cb.value));
  }

  const payload = {
    title: formData.get('title'),
    description: formData.get('description') || '',
    scope: formData.get('scope') || 'fidel',
    priority: formData.get('priority') || 'Media',
    frequency: freq,
    days_of_week: daysOfWeek,
    interval_days: parseInt(formData.get('interval_days') || 1),
    story_points: formData.get('story_points') ? parseFloat(formData.get('story_points')) : null
  };

  try {
    const res = await fetch('/api/recurrent/rules', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    if (res.ok) {
      showToast('Regla recurrente creada');
      closeModal('modal-create-rule');
      setTimeout(() => location.reload(), 400);
    } else {
      showToast('Error al crear regla', 'error');
    }
  } catch (err) {
    showToast('Error de conexión', 'error');
  }
}

// AI Effort Estimator Analyzer
let currentEstimation = null;

async function analyzeEffortWithAI(event) {
  event.preventDefault();
  const form = event.target;
  const formData = new FormData(form);

  const btn = document.getElementById('btn-analyze-ai');
  const loader = document.getElementById('ai-loader');
  const resultsCard = document.getElementById('ai-results-card');

  if (btn) btn.disabled = true;
  if (loader) loader.style.display = 'block';
  if (resultsCard) resultsCard.style.opacity = '0.4';

  const payload = {
    title: formData.get('title'),
    description: formData.get('description') || '',
    scope: formData.get('scope') || 'fidel',
    context: formData.get('context') || ''
  };

  try {
    const res = await fetch('/api/estimator/analyze', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    const data = await res.json();
    if (res.ok && data.status === 'ok') {
      currentEstimation = data.estimation;
      displayEstimationResults(data.estimation);
      showToast('Análisis de Gemini completado', 'success');
    } else {
      showToast('Fallo al analizar la tarea', 'error');
    }
  } catch (err) {
    showToast('Error de conexión con el servicio IA', 'error');
  } finally {
    if (btn) btn.disabled = false;
    if (loader) loader.style.display = 'none';
    if (resultsCard) resultsCard.style.opacity = '1';
  }
}

function displayEstimationResults(est) {
  const container = document.getElementById('ai-results-card');
  if (!container) return;

  container.style.display = 'flex';
  document.getElementById('res-sp').textContent = est.story_points || '2';
  document.getElementById('res-hours').textContent = `${est.estimated_hours || 2}h`;
  document.getElementById('res-complexity').textContent = est.complexity || 'Media';
  document.getElementById('res-summary').textContent = est.summary || '';

  // Select Fibonacci chip
  document.querySelectorAll('.fib-chip').forEach(chip => {
    chip.classList.toggle('selected', chip.textContent.trim() === String(est.story_points));
  });

  // Render Subtasks
  const subtasksList = document.getElementById('res-subtasks');
  subtasksList.innerHTML = '';
  (est.subtasks || []).forEach(st => {
    const div = document.createElement('div');
    div.className = 'checklist-item';
    div.innerHTML = `<span>✓</span> <span>${st}</span>`;
    subtasksList.appendChild(div);
  });

  // Render Risks
  const risksList = document.getElementById('res-risks');
  risksList.innerHTML = '';
  (est.risks_and_considerations || []).forEach(r => {
    const li = document.createElement('li');
    li.style.fontSize = '0.825rem';
    li.style.color = 'var(--text-secondary)';
    li.style.marginBottom = '0.35rem';
    li.textContent = r;
    risksList.appendChild(li);
  });

  // Show apply action button
  const applyBtn = document.getElementById('btn-apply-estimation');
  if (applyBtn) applyBtn.style.display = 'inline-flex';
}

// Apply Estimation as a Kanban Task
async function createFromEstimation() {
  if (!currentEstimation) return;

  const stage = document.getElementById('estimation-target-stage')?.value || 'todo';
  const priority = document.getElementById('estimation-target-priority')?.value || 'Media';

  const payload = {
    title: currentEstimation.title,
    description: `${currentEstimation.summary}\n\n*Estimado por Gemini: ${currentEstimation.story_points} SP (~${currentEstimation.estimated_hours}h)*`,
    scope: currentEstimation.scope || 'fidel',
    stage: stage,
    priority: priority,
    story_points: currentEstimation.story_points,
    estimated_hours: currentEstimation.estimated_hours,
    subtasks: currentEstimation.subtasks || []
  };

  try {
    const res = await fetch('/api/estimator/create-task', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    if (res.ok) {
      showToast('Tarea agregada al Tablero Kanban', 'success');
      setTimeout(() => {
        window.location.href = `/kanban?scope=${payload.scope}`;
      }, 700);
    } else {
      showToast('Error al crear tarea desde estimación', 'error');
    }
  } catch (err) {
    showToast('Error de conexión', 'error');
  }
}

// Initialize on DOM load
document.addEventListener('DOMContentLoaded', () => {
  initKanbanDragAndDrop();

  // Close modals on click outside
  document.querySelectorAll('.modal-overlay').forEach(overlay => {
    overlay.addEventListener('click', (e) => {
      if (e.target === overlay) {
        overlay.classList.remove('active');
      }
    });
  });
});
