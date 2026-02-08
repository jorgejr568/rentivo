/**
 * Dynamic formset management — add/remove form rows.
 *
 * Usage:
 *   <div id="formset-container" data-prefix="form">
 *     ... form rows ...
 *   </div>
 *   <button type="button" onclick="addFormRow('form')">Add</button>
 *
 * Each row should have class "formset-row" and contain an empty template
 * stored in a <template> element with id="${prefix}-empty-form".
 */

function addFormRow(prefix) {
  const container = document.getElementById(prefix + '-container');
  const template = document.getElementById(prefix + '-empty-form');
  const totalInput = document.getElementById('id_' + prefix + '-TOTAL_FORMS');

  if (!container || !template || !totalInput) return;

  const index = parseInt(totalInput.value);
  const newRow = template.content.cloneNode(true);

  // Replace __prefix__ with the actual index
  const html = newRow.querySelector('.formset-row');
  if (html) {
    html.innerHTML = html.innerHTML.replace(/__prefix__/g, index);
    container.appendChild(html);
  }

  totalInput.value = index + 1;
}

function removeFormRow(button, prefix) {
  const row = button.closest('.formset-row');
  if (!row) return;

  // If there's a DELETE checkbox (can_delete=True), check it and hide the row
  const deleteInput = row.querySelector('input[name$="-DELETE"]');
  if (deleteInput) {
    deleteInput.checked = true;
    row.classList.add('deleted-row');
    button.disabled = true;
    return;
  }

  // Otherwise remove the row and decrement total
  const totalInput = document.getElementById('id_' + prefix + '-TOTAL_FORMS');
  row.remove();

  // Re-index remaining rows
  const rows = document.querySelectorAll('#' + prefix + '-container .formset-row');
  rows.forEach((r, i) => {
    r.querySelectorAll('input, select, textarea').forEach(input => {
      if (input.name) {
        input.name = input.name.replace(
          new RegExp(prefix + '-\\d+-'),
          prefix + '-' + i + '-'
        );
      }
      if (input.id) {
        input.id = input.id.replace(
          new RegExp('id_' + prefix + '-\\d+-'),
          'id_' + prefix + '-' + i + '-'
        );
      }
    });
  });

  if (totalInput) {
    totalInput.value = rows.length;
  }
}
