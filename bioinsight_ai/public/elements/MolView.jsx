import React, { useEffect, useRef } from 'react';

export default function MolView() {
  const defaultProps = {
    cid: '3084463',
    regno: '5772',
    title: '3-D Molecular Viewer',
    mode: 'stick',
    bg: '0xC0C0C0'
  };

  const finalProps = { ...defaultProps, ...props };
  const { cid, regno, title, mode, bg } = finalProps;

  const viewerRef = useRef(null);

  // Define style mappings
  const styleMap = {
    stick: { stick: {} },
    sphere: { sphere: {} },
    line: { line: {} },
    wireframe: { wireframe: {} },
    vdw: { vdw: {} },
    cross: { cross: {} },
    balls: {
      stick: { radius: 0.12 },
      sphere: { scale: 0.22, opacity: 1.0 }
    }
  };

  // Use the selected style or default to stick
  const selectedStyle = styleMap[mode] || { stick: {} };

  useEffect(() => {
    const loadScript = (src) => {
      return new Promise((resolve, reject) => {
        const script = document.createElement('script');
        script.src = src;
        script.async = true;
        script.onload = resolve;
        script.onerror = reject;
        document.body.appendChild(script);
      });
    };

    const loadViewer = async () => {
      try {
        if (!window.$3Dmol) {
          await loadScript('https://3Dmol.org/build/3Dmol-min.js');
        }

        if (viewerRef.current) {
          const viewer = window.$3Dmol.createViewer(viewerRef.current, {
            backgroundColor: bg
          });

          const pubchemUrl = `https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/cid/${cid}/SDF?record_type=3d`;

          const response = await fetch(pubchemUrl);
          if (response.ok) {
            const sdfData = await response.text();
            viewer.addModel(sdfData, 'sdf');
            viewer.setStyle({}, selectedStyle);
            viewer.zoomTo();
            viewer.render();
            console.log(`Rendered using PubChem CID: ${cid}`);
          } else {
            const mwUrl = `https://www.metabolomicsworkbench.org/rest/compound/regno/${regno}/sdf`;
            const fallbackResponse = await fetch(mwUrl);
            if (fallbackResponse.ok) {
              const sdfData = await fallbackResponse.text();
              viewer.addModel(sdfData, 'sdf');
              viewer.setStyle({}, selectedStyle);
              viewer.zoomTo();
              viewer.render();
              console.log(`Rendered using Metabolomics Workbench regno: ${regno}`);
            } else {
              console.error('Failed to load structure from both PubChem and Metabolomics Workbench.');
            }
          }
        }
      } catch (err) {
        console.error('Error loading 3Dmol viewer or molecular data:', err);
      }
    };

    loadViewer();
  }, [cid, regno, mode, bg]);

  return (
    <div>
      <h3 style={{ fontWeight: 'bold' }}>{title}</h3>
      <div
        ref={viewerRef}
        style={{ width: '100%', maxWidth: '500px', height: '400px', position: 'relative' }}
      />
    </div>
  );
}