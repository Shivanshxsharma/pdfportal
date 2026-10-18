/**
 * tools.js — every tool, and which ones a set of files gets
 * ============================================================================
 * The ids are the engine's (engine/portal_engine/tools/__init__.py). This
 * file holds what only the UI needs: a short label that fits in a ring
 * slot, a one-line description for the disk, an icon, and whether the tool
 * needs a quick question first (a password, a page range).
 */

'use strict';

const TOOLS = {
  compress:      { label: 'Compress',  title: 'Compress PDF',     icon: 'compress', desc: 'Make it smaller to email or upload' },
  merge:         { label: 'Merge',     title: 'Merge into one',   icon: 'merge',    desc: 'Join them into one PDF, in this order' },
  split:         { label: 'Split',     title: 'Split PDF',        icon: 'split',    desc: 'One PDF per page, or your own ranges', form: 'split' },
  rotate:        { label: 'Rotate',    title: 'Rotate pages',     icon: 'rotate',   desc: 'Turn every page 90° clockwise' },
  pdf_to_images: { label: 'To JPG',    title: 'PDF to JPG',       icon: 'image',    desc: 'Save every page as a picture' },
  page_numbers:  { label: 'Numbers',   title: 'Add page numbers', icon: 'hash',     desc: 'Number every page at the bottom' },
  watermark:     { label: 'Watermark', title: 'Add a watermark',  icon: 'stamp',    desc: 'Stamp faint text across every page', form: 'watermark' },
  protect:       { label: 'Protect',   title: 'Protect PDF',      icon: 'lock',     desc: 'Lock it with a password', form: 'protect' },
  unlock:        { label: 'Unlock',    title: 'Unlock PDF',       icon: 'unlock',   desc: 'Remove its password' },
  images_to_pdf: { label: 'To PDF',    title: 'Images to PDF',    icon: 'pdf',      desc: 'Put the pictures into one PDF' },
};

const KINDS = {
  pdf: ['pdf'],
  image: ['jpg', 'jpeg', 'png', 'bmp', 'gif', 'tif', 'tiff', 'webp'],
  office: ['doc', 'docx', 'xls', 'xlsx', 'ppt', 'pptx', 'odt', 'ods', 'odp', 'rtf'],
};

function kindOf(path) {
  const ext = baseName(path).split('.').pop().toLowerCase();
  for (const [kind, exts] of Object.entries(KINDS)) if (exts.includes(ext)) return kind;
  return 'other';
}

/**
 * Which tools fit these files, in ring order (clockwise from the top).
 * Returns { tools: [...ids] } or { tools: [], problem: 'text for the disk' }.
 */
function toolsFor(paths) {
  const kinds = new Set(paths.map(kindOf));
  const only = (kind) => kinds.size === 1 && kinds.has(kind);
  const many = paths.length > 1;

  if (only('pdf')) {
    return {
      tools: [many ? 'merge' : 'split', 'compress', 'rotate', 'pdf_to_images', 'page_numbers', 'watermark', 'protect', 'unlock'],
    };
  }
  if (only('image')) return { tools: ['images_to_pdf'] };
  if ([...kinds].every((k) => k === 'pdf' || k === 'image')) return { tools: ['merge'] };
  if (kinds.has('office')) {
    return { tools: [], problem: 'Word, Excel and PowerPoint files are coming soon.' };
  }
  const odd = baseName(paths.find((p) => kindOf(p) === 'other') || '');
  const what = odd.includes('.') ? `.${odd.split('.').pop().toLowerCase()} files` : 'these files';
  return { tools: [], problem: `PDFportal can't work with ${what} yet.` };
}
