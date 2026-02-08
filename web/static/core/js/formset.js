/**
 * Formset management for dynamic form rows.
 *
 * Usage:
 *   <div id="formset-container" data-prefix="items">
 *     <!-- rows here -->
 *   </div>
 *   <button type="button" onclick="addFormsetRow('items')">Add</button>
 *   <input type="hidden" name="items-TOTAL_FORMS" id="id_items-TOTAL_FORMS" value="1">
 */

function addFormsetRow(prefix) {
    const container = document.getElementById(`${prefix}-container`);
    const totalInput = document.getElementById(`id_${prefix}-TOTAL_FORMS`);
    const total = parseInt(totalInput.value, 10);

    const template = document.getElementById(`${prefix}-empty-row`);
    if (!template) return;

    const html = template.innerHTML.replace(/__prefix__/g, total);
    const div = document.createElement('div');
    div.className = 'formset-row';
    div.id = `${prefix}-row-${total}`;
    div.innerHTML = html;
    container.appendChild(div);

    totalInput.value = total + 1;
}

function removeFormsetRow(prefix, index) {
    const row = document.getElementById(`${prefix}-row-${index}`);
    if (row) {
        row.remove();
    }
}
