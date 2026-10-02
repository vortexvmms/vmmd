// Shared saved-attendance checks. Submission remains an explicit supervisor action.
(function () {
  function status(rows, syncing) {
    const total = rows.length;
    const unmarked = rows.filter(x => !x.marked).length;
    const missing = rows.filter(x => x.present && !x.end_time).length;
    const submitted = total > 0 && rows.every(x => x.submitted);
    return {total, unmarked, missing, submitted,
      ready: total > 0 && !unmarked && !missing && !submitted && !syncing};
  }
  function sites(rows) {
    const groups = new Map();
    rows.forEach(row => {
      if ((row.site_name || '').trim().toUpperCase() === 'HOME LEAVE') return;
      if (!groups.has(row.site_id)) groups.set(row.site_id, []);
      groups.get(row.site_id).push(row);
    });
    return [...groups.values()].map(items => ({id:items[0].site_id,
      name:items[0].site_name, ...status(items, false)}));
  }
  window.VCMSAttendanceCompletion = {status, sites};
})();
