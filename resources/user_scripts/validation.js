import {parse} from 'acorn';
import {MAX_SCRIPTS} from './core.js';

export function validateScript(input) {
  if (!input || typeof input !== 'object') throw new Error('Invalid script.');
  if (typeof input.id !== 'string' || !/^[a-zA-Z0-9-]{1,64}$/.test(input.id)) throw new Error('Invalid script ID.');
  if (typeof input.name !== 'string' || !input.name.trim() || input.name.length > 120) throw new Error('Give the script a name of up to 120 characters.');
  if (typeof input.pattern !== 'string' || !input.pattern.trim() || input.pattern.length > 2048) throw new Error('Enter a URL regex of up to 2,048 characters.');
  try { new RegExp(input.pattern); } catch (error) { throw new Error('URL regex: ' + error.message); }
  if (!['start', 'load'].includes(input.timing)) throw new Error('Choose an execution time.');
  if (typeof input.enabled !== 'boolean') throw new Error('Invalid enabled state.');
  if (typeof input.code !== 'string' || !input.code.trim() || input.code.length > 262144) throw new Error('Enter JavaScript, up to 256 KiB per script.');
  try {
    const ast = parse('function run() {\n' + input.code + '\n}', {ecmaVersion: 'latest'});
    if (ast.body.length !== 1 || ast.body[0].type !== 'FunctionDeclaration') {
      throw new Error('The source must be one script body.');
    }
  }
  catch (error) {
    if (!error.loc) throw error;
    throw new Error(`JavaScript line ${Math.max(1, error.loc.line - 1)}, column ${error.loc.column + 1}: ${error.message.replace(/ \(\d+:\d+\)$/, '')}`);
  }
  return {id: input.id, name: input.name.trim(), pattern: input.pattern,
    timing: input.timing, enabled: input.enabled, code: input.code};
}

export function validateScripts(input) {
  if (!Array.isArray(input) || input.length > MAX_SCRIPTS) throw new Error(`Keep at most ${MAX_SCRIPTS} scripts.`);
  const result = input.map(validateScript);
  if (new Set(result.map(script => script.id)).size !== result.length) throw new Error('Duplicate script IDs.');
  return result;
}
