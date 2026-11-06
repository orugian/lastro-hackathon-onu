import {cp} from 'node:fs/promises';
await cp(new URL('../../data/artifacts-mock/', import.meta.url), new URL('../public/mock/',import.meta.url),{recursive:true});
console.log('Mock sincronizado em web/public/mock');
