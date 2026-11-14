import{a as e,i as t,n,t as r,v as i}from"./theme-vbfQFcMu.js";var a=e=>e.replace(/[&<>"]/g,e=>({"&":`&amp;`,"<":`&lt;`,">":`&gt;`,'"':`&quot;`})[e]);r(n()),i([...document.querySelectorAll(`[data-emergency]`)]),fetch(new URL(`data/meta.json`,document.baseURI),{cache:`no-cache`}).then(e=>e.json()).then(e=>{document.getElementById(`run`).textContent=`${e.weather_run} · model ${e.model}`,document.getElementById(`credits`).innerHTML=e.credits.map(e=>`
      <div class="card">
        <h3>${a(e.name)}</h3>
        <p>${a(e.credit)}</p>
        <p><span class="tag ${e.status===`verified`?``:`warn`}">${a(e.licence)}${e.status===`verified`?``:` · licence being checked`}</span></p>
        ${e.use?`<p>${a(e.use)}</p>`:``}
      </div>`).join(``)+`
      <div class="card"><h3>Protomaps basemap</h3><p>Map tiles from the Protomaps build of OpenStreetMap. © OpenStreetMap contributors (ODbL).</p></div>`});var o=[...e.map(e=>({name:e.latin,photos:e.photos})),...t.map(e=>({name:e.latin,photos:e.photos}))];document.getElementById(`photo-credits`).innerHTML=o.map(e=>e.photos.map(t=>`
  <li><i>${a(t.taxon??e.name)}</i>: <a href="${a(t.page)}" target="_blank" rel="noopener">${a(t.attribution)}</a></li>`).join(``)).join(``);