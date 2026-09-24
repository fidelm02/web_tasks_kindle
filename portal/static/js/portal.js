/**
 * Kindle Tasks Pro Portal - Interactive Engine
 * Handles Drag & Drop, AJAX updates, Stage transitions, Crons triggers,
 * Gemini AI analysis for new and existing tasks, Table view, Calendar & Google Calendar integration.
 */

let activeDetailTask = null;
let currentExistingAnalysis = null;
let contextMenuTargetTask = null;

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

// Quick Stage Select Change (Kanban)
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

// Quick Stage Select Change (Table View)
async function handleTableStageChange(taskId, scope, newStage) {
  try {
    const res = await fetch('/api/tasks/move', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        task_id: taskId,
        target_stage: newStage,
        scope: scope
      })
    });
    if (res.ok) {
      showToast('Etapa actualizada');
    } else {
      showToast('Error al actualizar etapa', 'error');
    }
  } catch (err) {
    showToast('Error de red', 'error');
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
    target_date: formData.get('target_date') || null,
    start_time: formData.get('start_time') || null,
    end_time: formData.get('end_time') || null
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
      const row = document.getElementById(`table-row-${taskId}`);
      if (row) row.remove();
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
  activeDetailTask = task;

  const codeBadge = document.getElementById('detail-code-badge');
  if (codeBadge) codeBadge.textContent = task.code || 'ID';

  document.getElementById('detail-task-id').value = task.id;
  document.getElementById('detail-scope').value = task.scope || 'fidel';
  document.getElementById('detail-title').value = task.title || '';
  document.getElementById('detail-description').value = task.description || '';
  document.getElementById('detail-stage').value = task.stage || 'todo';
  document.getElementById('detail-priority').value = task.priority || 'Media';
  document.getElementById('detail-sp').value = task.story_points || '';
  document.getElementById('detail-hours').value = task.estimated_hours || '';
  document.getElementById('detail-date').value = task.target_date || '';

  const startTimeElem = document.getElementById('detail-start-time');
  if (startTimeElem) startTimeElem.value = task.start_time || '';

  const endTimeElem = document.getElementById('detail-end-time');
  if (endTimeElem) endTimeElem.value = task.end_time || '';

  const gcalBtn = document.getElementById('detail-gcal-link');
  if (gcalBtn) gcalBtn.href = task.google_cal_url || '#';

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

// Trigger AI Analysis from inside detail modal
function triggerAnalyzeFromDetailModal() {
  if (!activeDetailTask) return;
  closeModal('modal-task-detail');
  analyzeTaskWithAi(activeDetailTask.id, activeDetailTask.scope);
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
    target_date: formData.get('target_date') || null,
    start_time: formData.get('start_time') || null,
    end_time: formData.get('end_time') || null
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

// Recurrent Rule Edit Modal Populate
function openEditRuleModal(ruleJson) {
  const rule = typeof ruleJson === 'string' ? JSON.parse(ruleJson) : ruleJson;
  document.getElementById('edit-rule-id').value = rule.id;
  document.getElementById('edit-rule-title').value = rule.title || '';
  document.getElementById('edit-rule-desc').value = rule.description || '';
  document.getElementById('edit-rule-scope').value = rule.scope || 'fidel';
  document.getElementById('edit-rule-priority').value = rule.priority || 'Media';
  document.getElementById('edit-rule-freq').value = rule.frequency || 'daily';
  document.getElementById('edit-rule-sp').value = rule.story_points || '';
  document.getElementById('edit-rule-interval').value = rule.interval_days || 1;

  // Toggle custom days vs interval display
  const customGroup = document.getElementById('edit-custom-days-group');
  const intervalGroup = document.getElementById('edit-interval-days-group');
  if (customGroup) customGroup.style.display = rule.frequency === 'custom_days' ? 'block' : 'none';
  if (intervalGroup) intervalGroup.style.display = rule.frequency === 'interval_days' ? 'block' : 'none';

  // Set day checkboxes
  const daysOfWeek = rule.days_of_week || [];
  document.querySelectorAll('input[name="edit_custom_day"]').forEach(cb => {
    cb.checked = daysOfWeek.includes(parseInt(cb.value));
  });

  openModal('modal-edit-rule');
}

// Submit Recurrent Rule Edit
async function submitUpdateRule(event) {
  event.preventDefault();
  const form = event.target;
  const formData = new FormData(form);
  const ruleId = formData.get('rule_id');

  const freq = formData.get('frequency');
  let daysOfWeek = [0, 1, 2, 3, 4, 5, 6];
  if (freq === 'weekdays') {
    daysOfWeek = [0, 1, 2, 3, 4];
  } else if (freq === 'custom_days') {
    daysOfWeek = Array.from(form.querySelectorAll('input[name="edit_custom_day"]:checked')).map(cb => parseInt(cb.value));
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
    const res = await fetch(`/api/recurrent/rules/${ruleId}/update`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    if (res.ok) {
      showToast('Regla actualizada con éxito');
      closeModal('modal-edit-rule');
      setTimeout(() => location.reload(), 400);
    } else {
      showToast('Error al actualizar regla', 'error');
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

// AI Analysis for Existing Task
async function analyzeTaskWithAi(taskId, scope) {
  openModal('modal-ai-existing-analysis');
  const loading = document.getElementById('ai-existing-loading');
  const content = document.getElementById('ai-existing-content');
  const footer = document.getElementById('ai-existing-footer');

  if (loading) loading.style.display = 'block';
  if (content) content.style.display = 'none';
  if (footer) footer.style.display = 'none';

  try {
    const res = await fetch('/api/estimator/analyze-existing', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ task_id: taskId, scope: scope })
    });
    const data = await res.json();
    if (res.ok && data.status === 'ok') {
      currentExistingAnalysis = data;
      displayExistingTaskAnalysis(data.estimation, data.task);
    } else {
      showToast('No se pudo analizar la tarea con Gemini', 'error');
      closeModal('modal-ai-existing-analysis');
    }
  } catch (err) {
    showToast('Error de conexión con el servicio IA', 'error');
    closeModal('modal-ai-existing-analysis');
  } finally {
    if (loading) loading.style.display = 'none';
  }
}

function displayExistingTaskAnalysis(est, task) {
  const content = document.getElementById('ai-existing-content');
  const footer = document.getElementById('ai-existing-footer');
  if (content) content.style.display = 'flex';
  if (footer) footer.style.display = 'flex';

  document.getElementById('ai-task-target-title').textContent = `[${task.code || 'ID'}] ${task.title}`;
  document.getElementById('ai-task-complexity').textContent = est.complexity || 'Media';
  document.getElementById('ai-task-sp').textContent = `${est.story_points || 2} SP`;
  document.getElementById('ai-task-hours').textContent = `${est.estimated_hours || 3}h`;
  document.getElementById('ai-task-summary').textContent = est.summary || '';

  // Recurrent Recommendation
  const recHeader = document.getElementById('ai-task-recurrent-header');
  const recReason = document.getElementById('ai-task-recurrent-reason');
  const convertBox = document.getElementById('ai-task-convert-box');

  if (est.is_recurrent_candidate) {
    recHeader.innerHTML = '✨ ¡Candidato ideal para automatización recurrente!';
    recHeader.style.color = '#a5b4fc';
    convertBox.style.display = 'block';
  } else {
    recHeader.innerHTML = '📌 Tarea puntual / No recurrente';
    recHeader.style.color = 'var(--text-secondary)';
    convertBox.style.display = 'none';
  }
  recReason.textContent = est.recurrent_reasoning || 'Evaluación de periodicidad completada.';

  // Render Subtasks
  const subtasksList = document.getElementById('ai-task-subtasks');
  subtasksList.innerHTML = '';
  (est.subtasks || []).forEach(st => {
    const div = document.createElement('div');
    div.className = 'checklist-item';
    div.innerHTML = `<span>✓</span> <span>${st}</span>`;
    subtasksList.appendChild(div);
  });

  // Render Risks
  const risksList = document.getElementById('ai-task-risks');
  risksList.innerHTML = '';
  (est.risks_and_considerations || []).forEach(r => {
    const li = document.createElement('li');
    li.style.fontSize = '0.825rem';
    li.style.color = 'var(--text-secondary)';
    li.style.marginBottom = '0.25rem';
    li.textContent = r;
    risksList.appendChild(li);
  });
}

// Apply Analysis in-place to Existing Task
async function applyAiAnalysisToExistingTask() {
  if (!currentExistingAnalysis) return;
  const { estimation, task } = currentExistingAnalysis;

  try {
    const res = await fetch('/api/estimator/apply-to-task', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        task_id: task.id,
        scope: task.scope,
        story_points: estimation.story_points,
        estimated_hours: estimation.estimated_hours,
        subtasks: estimation.subtasks || [],
        summary: estimation.summary
      })
    });
    if (res.ok) {
      showToast('Estimación aplicada a la tarea exitosamente', 'success');
      closeModal('modal-ai-existing-analysis');
      setTimeout(() => location.reload(), 500);
    } else {
      showToast('Error al aplicar estimación', 'error');
    }
  } catch (err) {
    showToast('Error de conexión', 'error');
  }
}

// Convert Current Task to Recurrent Rule
async function convertCurrentTaskToRecurrent() {
  if (!currentExistingAnalysis) return;
  const { estimation, task } = currentExistingAnalysis;

  const freq = estimation.suggested_frequency && estimation.suggested_frequency !== 'none'
    ? estimation.suggested_frequency
    : 'daily';

  try {
    const res = await fetch('/api/estimator/convert-to-recurrent', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        task_id: task.id,
        scope: task.scope,
        frequency: freq,
        story_points: estimation.story_points
      })
    });
    if (res.ok) {
      showToast('¡Regla recurrente creada con éxito!', 'success');
      closeModal('modal-ai-existing-analysis');
      setTimeout(() => {
        window.location.href = '/recurrent';
      }, 700);
    } else {
      showToast('Error al crear regla recurrente', 'error');
    }
  } catch (err) {
    showToast('Error de conexión', 'error');
  }
}

// Context Menu (Right Click on Card)
function handleCardContextMenu(event, task) {
  event.preventDefault();
  contextMenuTargetTask = task;
  const menu = document.getElementById('card-context-menu');
  if (!menu) return;

  menu.style.display = 'block';
  menu.style.left = `${Math.min(event.clientX, window.innerWidth - 230)}px`;
  menu.style.top = `${Math.min(event.clientY, window.innerHeight - 200)}px`;
}

function contextMenuAction(action) {
  const menu = document.getElementById('card-context-menu');
  if (menu) menu.style.display = 'none';
  if (!contextMenuTargetTask) return;

  const task = contextMenuTargetTask;
  if (action === 'analyze') {
    analyzeTaskWithAi(task.id, task.scope);
  } else if (action === 'edit') {
    openTaskDetailModal(task);
  } else if (action === 'calendar') {
    window.open(task.google_cal_url || '#', '_blank');
  } else if (action === 'recurrent') {
    analyzeTaskWithAi(task.id, task.scope);
  } else if (action === 'delete') {
    deleteTask(task.id, task.scope);
  }
}

// Calendar Helpers
function quickScheduleDay(dateStr) {
  openModal('modal-create-task');
  const dateInput = document.querySelector('#modal-create-task input[name="target_date"]');
  if (dateInput) dateInput.value = dateStr;
}

async function quickAssignToday(taskId, scope) {
  const todayStr = new Date().toISOString().split('T')[0];
  try {
    const res = await fetch('/api/tasks/update', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        task_id: taskId,
        scope: scope,
        target_date: todayStr,
        start_time: '10:00',
        end_time: '11:00'
      })
    });
    if (res.ok) {
      showToast('Tarea programada para hoy a las 10:00');
      setTimeout(() => location.reload(), 400);
    } else {
      showToast('Error al programar tarea', 'error');
    }
  } catch (err) {
    showToast('Error de red', 'error');
  }
}

// Open Day Detail Pop-up Modal with complete task information
function openDayDetailModal(dateStr, tasksJson) {
  const tasks = typeof tasksJson === 'string' ? JSON.parse(tasksJson) : (tasksJson || []);
  
  if (!dateStr) return;
  const parts = dateStr.split('-');
  const dateObj = new Date(parseInt(parts[0]), parseInt(parts[1]) - 1, parseInt(parts[2]));
  const weekday = dateObj.toLocaleDateString('es-ES', { weekday: 'long' });
  const fullDate = dateObj.toLocaleDateString('es-ES', { day: 'numeric', month: 'long', year: 'numeric' });

  const weekdayElem = document.getElementById('day-modal-weekday');
  if (weekdayElem) weekdayElem.textContent = weekday;

  const titleElem = document.getElementById('day-modal-title');
  if (titleElem) titleElem.textContent = fullDate.charAt(0).toUpperCase() + fullDate.slice(1);

  const addBtn = document.getElementById('day-modal-add-btn');
  if (addBtn) {
    addBtn.onclick = () => {
      closeModal('modal-day-tasks');
      quickScheduleDay(dateStr);
    };
  }

  let totalSp = 0;
  tasks.forEach(t => {
    const sp = parseFloat(t.story_points || 0);
    if (!isNaN(sp)) totalSp += sp;
  });

  const spBadge = document.getElementById('day-modal-sp-badge');
  if (spBadge) spBadge.textContent = `${totalSp.toFixed(1)} SP`;

  const countElem = document.getElementById('day-modal-count');
  if (countElem) countElem.textContent = `${tasks.length} ${tasks.length === 1 ? 'tarea registrada' : 'tareas registradas'}`;

  const container = document.getElementById('day-modal-tasks-list');
  if (!container) return;
  container.innerHTML = '';

  if (tasks.length === 0) {
    container.innerHTML = `
      <div style="text-align:center; padding:2.5rem 1rem; color:var(--text-muted);">
        <p style="font-size:1rem; margin-bottom:0.75rem;">No hay tareas programadas para este día.</p>
        <button class="btn btn-primary btn-sm" onclick="closeModal('modal-day-tasks'); quickScheduleDay('${dateStr}');">
          + Programar una tarea aquí
        </button>
      </div>
    `;
  } else {
    tasks.forEach(task => {
      const card = document.createElement('div');
      card.className = 'day-task-card';

      const timeSlotHtml = task.start_time
        ? `<span style="font-size:0.75rem; color:#93c5fd; background:rgba(59,130,246,0.15); padding:0.15rem 0.5rem; border-radius:var(--radius-sm); font-weight:600;">⏰ ${task.start_time}${task.end_time ? ' - ' + task.end_time : ''}</span>`
        : `<span style="font-size:0.75rem; color:var(--text-muted);">Sin horario específico</span>`;

      const subtasksInfo = (task.subtasks_count > 0)
        ? `<span class="subtasks-progress" style="font-size:0.75rem;">✓ ${task.subtasks_completed}/${task.subtasks_count} subtareas completadas</span>`
        : '';

      const taskJsonEscaped = JSON.stringify(task).replace(/"/g, '&quot;');

      card.innerHTML = `
        <div style="display:flex; justify-content:space-between; align-items:flex-start; gap:0.5rem;">
          <div style="display:flex; align-items:center; gap:0.4rem; flex-wrap:wrap;">
            <span class="card-scope-badge" style="background:rgba(59,130,246,0.2); color:#93c5fd; font-weight:700;">${task.code || 'ID'}</span>
            <span class="card-scope-badge">${task.scope}</span>
            <span class="priority-pill priority-${(task.priority || 'media').toLowerCase()}">${task.priority}</span>
            <span class="priority-pill" style="background:rgba(139,92,246,0.15); color:#c4b5fd;">${(task.stage || 'todo').replace('_', ' ').toUpperCase()}</span>
            ${task.story_points ? `<span class="sp-badge">🎯 ${task.story_points} SP</span>` : ''}
          </div>
          <div>${timeSlotHtml}</div>
        </div>

        <div style="font-size:1rem; font-weight:700; color:var(--text-primary); cursor:pointer;" onclick="closeModal('modal-day-tasks'); openTaskDetailModal(${taskJsonEscaped})">
          ${task.title}
        </div>

        ${task.description ? `<p style="font-size:0.825rem; color:var(--text-secondary); line-height:1.4; margin:0;">${task.description}</p>` : ''}
        ${subtasksInfo}

        <div style="display:flex; justify-content:space-between; align-items:center; border-top:1px solid var(--border-subtle); padding-top:0.6rem; margin-top:0.2rem; flex-wrap:wrap; gap:0.5rem;">
          <div style="display:flex; gap:0.35rem; align-items:center;">
            <a href="${task.google_cal_url || '#'}" target="_blank" class="btn btn-secondary btn-sm" title="Bloquear evento en Google Calendar">
              <span>📅</span>
              <span>Google Cal</span>
            </a>
            <button class="btn btn-secondary btn-sm" onclick="closeModal('modal-day-tasks'); analyzeTaskWithAi('${task.id}', '${task.scope}')" title="Analizar con Gemini">
              <span>✨</span>
              <span>IA</span>
            </button>
            <button class="btn btn-secondary btn-sm" onclick="closeModal('modal-day-tasks'); openTaskDetailModal(${taskJsonEscaped})" title="Ver o editar detalles">
              <span>✏️</span>
              <span>Detalles</span>
            </button>
          </div>

          <div style="display:flex; gap:0.4rem; align-items:center;">
            <select class="quick-move-select" onchange="handleTableStageChange('${task.id}', '${task.scope}', this.value)" title="Mover etapa">
              <option value="backlog" ${task.stage === 'backlog' ? 'selected' : ''}>Backlog</option>
              <option value="todo" ${task.stage === 'todo' ? 'selected' : ''}>Por Hacer</option>
              <option value="in_progress" ${task.stage === 'in_progress' ? 'selected' : ''}>En Progreso</option>
              <option value="review" ${task.stage === 'review' ? 'selected' : ''}>En Revisión</option>
              <option value="done" ${task.stage === 'done' ? 'selected' : ''}>Completado</option>
            </select>
            <button class="btn btn-danger btn-sm" onclick="deleteTask('${task.id}', '${task.scope}'); closeModal('modal-day-tasks');" title="Eliminar tarea">
              🗑
            </button>
          </div>
        </div>
      `;
      container.appendChild(card);
    });
  }

  openModal('modal-day-tasks');
}


// Close Context Menu on Global Click
document.addEventListener('click', (e) => {
  const menu = document.getElementById('card-context-menu');
  if (menu && menu.style.display === 'block') {
    if (!e.target.closest('#card-context-menu')) {
      menu.style.display = 'none';
    }
  }
});

// AI Effort Estimator Analyzer (Estimator Page)
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
