<!-- LOVABLE:BEGIN -->
> [!IMPORTANT]
> This project is connected to [Lovable](https://lovable.dev). Avoid rewriting
> published git history — force pushing, or rebasing/amending/squashing commits
> that are already pushed — as it rewrites history on Lovable's side and the
> user will likely lose their project history.
>
> Commits you push to the connected branch sync back to Lovable and show up in
> the editor, so keep the branch in a working state.
<!-- LOVABLE:END -->

- Practice data is bundled as static JSON in src/data (CSV converted once); all parsing/tokenising lives in src/lib/hooly.ts so pages stay presentational.
- Fact tree, event anchoring and true/false/unsure checking live in src/lib/tree.ts (sentence verdict = AND of fact verdicts) so the final product reuses one checker.
- New-claim generation lives in src/lib/claims.ts: candidates come from tree.ts segments (per value slot), and every claim passes a referee-style text validator before output so the challenge's wording rules hold.
