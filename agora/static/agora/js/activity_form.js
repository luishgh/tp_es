function setHidden(el, hidden) {
  if (!el) return;
  el.hidden = hidden;
}

function setDisabledWithin(container, disabled) {
  if (!container) return;
  const fields = container.querySelectorAll('input, select, textarea, button');
  fields.forEach((field) => {
    field.disabled = disabled;
  });
}

function updateActivityFormVisibility() {
  const typeSelect = document.querySelector('.js-activity-type');
  const allFields = document.querySelector('.js-activity-fields');
  const assignmentFields = document.querySelector('.js-fields-assignment');
  const resourceFields = document.querySelector('.js-fields-resource');

  if (!typeSelect || !allFields) return;

  const type = typeSelect.value;
  const hasType = type === 'assignment' || type === 'resource';

  setHidden(allFields, !hasType);
  setDisabledWithin(allFields, !hasType);

  const showAssignment = type === 'assignment';
  const showResource = type === 'resource';

  setHidden(assignmentFields, !showAssignment);
  setDisabledWithin(assignmentFields, !showAssignment);

  setHidden(resourceFields, !showResource);
  setDisabledWithin(resourceFields, !showResource);
}

document.addEventListener('DOMContentLoaded', () => {
  const typeSelect = document.querySelector('.js-activity-type');
  if (!typeSelect) return;

  updateActivityFormVisibility();
  typeSelect.addEventListener('change', updateActivityFormVisibility);
});

