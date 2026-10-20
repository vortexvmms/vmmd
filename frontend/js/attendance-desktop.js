// Move the existing controls at the desktop breakpoint, retaining their state
// and handlers. Placeholders restore the original phone order on resize.
(function () {
  'use strict';
  const desktop = matchMedia('(min-width:900px)');
  const header = document.querySelector('#attendance-page-header .vcms-page-header__row');
  const tools = document.getElementById('att-footer-tools');
  const options = document.createElement('details');
  options.id = 'att-bulk-options';
  const summary = document.createElement('summary');
  summary.textContent = 'More options';
  options.append(summary);

  const moves = [
    ['.vcms-page-toolbar', header],
    ['#att-kpis', header],
    ['#att-filters', document.getElementById('att-statusline')],
    ['#morningbar', tools],
    ['#bulkbar', tools],
    ['#bulkbar .bulk-help', options],
    ['#groupbar', tools],
  ].map(([selector, target]) => {
    const node = document.querySelector(selector);
    const home = document.createComment('Original position: ' + selector);
    node.before(home);
    return {node, home, target};
  });

  function arrange() {
    document.body.classList.toggle('att-compact-desktop', desktop.matches);
    if (desktop.matches) {
      moves.forEach(({node, target}) => target.append(node));
      document.getElementById('bulkbar').append(options);
    } else {
      moves.forEach(({node, home}) => home.after(node));
      options.remove();
      options.open = false;
    }
    measureFooter();
  }

  // The footer may grow at narrow widths, with a selected group, or when text
  // is enlarged. Reserve its actual height so the last worker stays reachable.
  function measureFooter() {
    document.body.style.setProperty('--att-footer-height',
      document.getElementById('att-actions').getBoundingClientRect().height + 'px');
    document.body.style.setProperty('--att-group-height',
      document.getElementById('groupbar').getBoundingClientRect().height + 'px');
  }
  const sizes = new ResizeObserver(measureFooter);
  sizes.observe(document.getElementById('att-actions'));
  sizes.observe(document.getElementById('groupbar'));
  desktop.addEventListener('change', arrange);
  document.addEventListener('keydown', event => {
    if (event.key === 'Escape' && options.open) {
      options.open = false;
      summary.focus();
    }
  });
  document.addEventListener('click', event => {
    if (!options.contains(event.target)) options.open = false;
  });
  arrange();
})();
