//! Small deterministic, class-balanced random forest. No runtime dependencies.

#[derive(Clone)]
enum Node {
    Leaf([f64; 3]),
    Split {
        feature: usize,
        threshold: f64,
        left: Box<Node>,
        right: Box<Node>,
    },
}

#[derive(Clone)]
pub struct RandomForest {
    trees: Vec<Node>,
}

struct Rng(u64);
impl Rng {
    fn next(&mut self) -> u64 {
        self.0 ^= self.0 << 13;
        self.0 ^= self.0 >> 7;
        self.0 ^= self.0 << 17;
        self.0
    }
    fn index(&mut self, length: usize) -> usize {
        (self.next() as usize) % length
    }
}

impl RandomForest {
    pub fn train(features: &[Vec<f64>], labels: &[usize]) -> Self {
        if features.is_empty() {
            return Self {
                trees: vec![Node::Leaf([1.0 / 3.0; 3])],
            };
        }
        let mut classes = [Vec::new(), Vec::new(), Vec::new()];
        for (index, &label) in labels.iter().enumerate() {
            classes[label].push(index);
        }
        let available: Vec<usize> = (0..3).filter(|&c| !classes[c].is_empty()).collect();
        let mut rng = Rng(0x5eed_2026_1028);
        let trees = (0..96)
            .map(|_| {
                let sample: Vec<usize> = (0..features.len())
                    .map(|_| {
                        let class = available[rng.index(available.len())];
                        classes[class][rng.index(classes[class].len())]
                    })
                    .collect();
                build(features, labels, &sample, 0, &mut rng)
            })
            .collect();
        Self { trees }
    }

    pub fn predict(&self, features: &[f64]) -> [f64; 3] {
        let mut total = [0.0; 3];
        for tree in &self.trees {
            let mut node = tree;
            while let Node::Split {
                feature,
                threshold,
                left,
                right,
            } = node
            {
                node = if features.get(*feature).copied().unwrap_or(0.0) <= *threshold {
                    left
                } else {
                    right
                };
            }
            if let Node::Leaf(probabilities) = node {
                for (sum, p) in total.iter_mut().zip(probabilities) {
                    *sum += p;
                }
            }
        }
        let sum: f64 = total.iter().sum();
        total.map(|p| p / sum)
    }

    pub fn tree_count(&self) -> usize {
        self.trees.len()
    }
}

fn gini(counts: &[f64; 3]) -> f64 {
    let total: f64 = counts.iter().sum();
    if total == 0.0 {
        return 0.0;
    }
    total - counts.iter().map(|n| n * n / total).sum::<f64>()
}

fn build(x: &[Vec<f64>], y: &[usize], indices: &[usize], depth: usize, rng: &mut Rng) -> Node {
    let mut counts = [0.0; 3];
    for &i in indices {
        counts[y[i]] += 1.0;
    }
    let leaf = || {
        let total = indices.len() as f64 + 3.0;
        Node::Leaf(counts.map(|n| (n + 1.0) / total))
    };
    if depth >= 11 || indices.len() < 10 || gini(&counts) < 0.01 {
        return leaf();
    }
    let feature_count = x[0].len();
    let mut best: Option<(f64, usize, f64)> = None;
    for _ in 0..16 {
        let feature = rng.index(feature_count);
        for _ in 0..12 {
            let a = x[indices[rng.index(indices.len())]][feature];
            let b = x[indices[rng.index(indices.len())]][feature];
            let threshold = (a + b) / 2.0;
            let mut left = [0.0; 3];
            let mut right = counts;
            let mut left_n = 0;
            for &i in indices {
                if x[i][feature] <= threshold {
                    left[y[i]] += 1.0;
                    right[y[i]] -= 1.0;
                    left_n += 1;
                }
            }
            if left_n < 4 || indices.len() - left_n < 4 {
                continue;
            }
            let cost = gini(&left) + gini(&right);
            if best.is_none_or(|(old, _, _)| cost < old) {
                best = Some((cost, feature, threshold));
            }
        }
    }
    let Some((cost, feature, threshold)) = best else {
        return leaf();
    };
    if cost >= gini(&counts) - 1e-8 {
        return leaf();
    }
    let (left, right): (Vec<usize>, Vec<usize>) = indices
        .iter()
        .copied()
        .partition(|&i| x[i][feature] <= threshold);
    Node::Split {
        feature,
        threshold,
        left: Box::new(build(x, y, &left, depth + 1, rng)),
        right: Box::new(build(x, y, &right, depth + 1, rng)),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn separates_classes_and_is_seeded() {
        let features: Vec<Vec<f64>> = (0..180).map(|i| vec![i as f64]).collect();
        let labels: Vec<usize> = (0..180).map(|i| i / 60).collect();
        let a = RandomForest::train(&features, &labels);
        let b = RandomForest::train(&features, &labels);
        for (point, class) in [(15.0, 0), (90.0, 1), (165.0, 2)] {
            let p = a.predict(&[point]);
            assert!(p[class] > 0.7, "{p:?}");
            assert_eq!(p, b.predict(&[point]));
            assert!((p.iter().sum::<f64>() - 1.0).abs() < 1e-9);
        }
    }
}
