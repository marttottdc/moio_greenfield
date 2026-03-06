import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

function getNextBuildNumber() {
  // Deprecated: avoid writing dotfiles in build contexts (CI/container).
  // Keep for backward compatibility but never write to disk.
  return 1;
}

function generateBuildInfo() {
  const timestamp = Date.now();
  const buildDate = new Date().toISOString();
  
  const githubRunNumber = process.env.GITHUB_RUN_NUMBER?.toString().trim();
  const githubSha = process.env.GITHUB_SHA?.toString().trim();
  const commit = githubSha || process.env.SOURCE_VERSION?.toString().trim() || process.env.VERCEL_GIT_COMMIT_SHA?.toString().trim();

  // Prefer CI run number when available; fall back to local incrementer.
  const buildNumber = githubRunNumber ? parseInt(githubRunNumber, 10) : undefined;
  const safeBuildNumber = Number.isFinite(buildNumber) ? buildNumber : undefined;
  const buildId = githubRunNumber ? `gha-${githubRunNumber}` : `local-${timestamp}`;
  const commitShort = commit ? commit.slice(0, 8) : undefined;
  
  const packageJsonPath = path.join(__dirname, '..', 'package.json');
  const packageJson = JSON.parse(fs.readFileSync(packageJsonPath, 'utf8'));
  const version = packageJson.version || '1.0.0';
  
  const buildInfo = {
    version,
    buildId,
    buildNumber: safeBuildNumber,
    buildDate,
    timestamp,
    commit,
    commitShort,
  };
  
  const publicDir = path.join(__dirname, '..', 'client', 'public');
  if (!fs.existsSync(publicDir)) {
    fs.mkdirSync(publicDir, { recursive: true });
  }
  
  const metaJsonPath = path.join(publicDir, 'meta.json');
  fs.writeFileSync(metaJsonPath, JSON.stringify(buildInfo, null, 2));
  console.log(`[BUILD] Generated meta.json (${buildId}${commitShort ? ` • ${commitShort}` : ""})`);
  
  return buildInfo;
}

generateBuildInfo();
