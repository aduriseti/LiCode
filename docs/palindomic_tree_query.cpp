/*
You are given an undirected tree with n nodes labeled 0 to n - 1. This is
represented by a 2D array edges of length n - 1, where edges[i] = [ui, vi]
indicates an undirected edge between nodes ui and vi.

You are also given a string s of length n consisting of lowercase English
letters, where s[i] represents the character assigned to node i.

You are also given a string array queries, where each queries[i] is either:
- "update ui c": Change the character at node ui to c. Formally, update s[ui] = c.
- "query ui vi": Determine whether the string formed by the characters on the
  unique path from ui to vi (inclusive) can be rearranged into a palindrome.

Return a boolean array answer, where answer[j] is true if the jth query of type
"query ui vi"​​​​​​​ can be rearranged into a palindrome, and false otherwise.

Solution:
each node in the tree should track what characters are present in the subtree
under that node

inserts can be accomplished in O(log(N)) if tree is balanced - ah but tree may
not be balanced

i realize that we only need to care about character counts on path to tree root

updates and queries must run in logN time based on problem contraints

what about prefix sum per node? - no same issue where an insert requires
potentially N operations

what about a segment tree-like datastructure?
where we compute the # of characters in the tree ring from depth 0 to d/2 (where d is max depth)
and from d/2 to d

and do so recursively

then when we want to find # of characters for a specific node of depth d

we look

Solution:
OK - will use a combinatoin of euler tour + xor bitmask + binary lifting +
fenwick tree (segment tree) to compute this

euler tour will be used to flatten the tree into an array - we will also for
each node record the start/end of the interval of the flattened array
corresponding to its subtree

we will use a segment tree to store the XOR SUM of the path from root to a
node 

then to compute the XOR bitmask of characters b/w 2 nodes n,m - we will need to
1. find the LCA
2. XOR(n) ^ XOR(m) ^ XOR(LCA)

we can then cehck if at most 1 character hs an odd count in this bitmask

we can find the LCA in logN time using binary lifting

Update:
actually - we will use a fenwick tree to compute the XOR sum along the path
from root to a node

fenwich tree suports query[i] which returns the prefix sum (or XOR) of the
array[0:i+1] - thsi can be used to perform range queries on the underlying
array

we dont want the XOR sum for entire subarray of each node - we want instead
the XOR sum alogn the path from root to a node

we will do this by making the virtual underlying array of the fenwick tree
store the XOR difference array of the trees euler tour

*/

// !wget -O dbg.h https://raw.githubusercontent.com/sharkdp/dbg-macro/master/dbg.h

%%writefile main.cpp
#include <iostream>
#include <vector>
#include <string>
#include <algorithm>
#include <map>
#include <sstream>
#include <functional>

using namespace std;

struct FenwickTree {
  int n;
  std::vector<int> tree;

  FenwickTree(int n):
    n(n),
    tree(n+1,0) {}
  
  void update(int i, int val) {
    ++i; // covert to 1-indexed
    for(; i<=n; i += (i & -i)) {
      tree[i] ^= val;
    }
  }

  int query(int i) {
    int res = 0;
    ++i; // convert to 1-indexed
    for (; 0<i; i -= (i & -i)) {
      res ^= tree[i];
    }
    return res;
  }
};

class Solution {
public:
    vector<bool> palindromePath(int n, vector<vector<int>>& edges, string s, vector<string>& queries) {
        std::vector<int> euler_tour;
        std::vector<int> euler_in(n,-1);
        std::vector<int> euler_out(n,-1);
        std::vector<vector<int>> graph(n);
        for (auto uv : edges) {
          graph[uv[0]].push_back(uv[1]);
          graph[uv[1]].push_back(uv[0]);
        }
        vector<vector<int>> up(n, vector<int>(32));
        const int LOG = 32;
        std::function<void(int, int)> dfs = [&](int node, int parent) {
          euler_in[node] = euler_tour.size();
          euler_tour.push_back(node);

          // Standard Binary Lifting precalc
          up[node][0] = (parent == -1) ? node : parent; 
          for (int i = 1; i < LOG; ++i) {
              up[node][i] = up[up[node][i-1]][i-1];
          }

          for (int neighbor : graph[node]) {
            if (neighbor != parent) dfs(neighbor, node);
          }

          euler_out[node] = euler_tour.size();
        };
        dfs(0, -1);

        auto is_ancestor = [&](int u, int v) {
          return euler_in[u] <= euler_in[v] && euler_out[u] >= euler_out[v];
        };

        FenwickTree tree(n+1);
        auto char_bitmask = [](char c) {
          return 1 << (c - 'a'); 
        };
        auto fenwick_tree_populate = [&](int node, char c) {
          tree.update(euler_in[node], char_bitmask(c));
          tree.update(euler_out[node], char_bitmask(c));
        };
        for (int i = 0; i < n; ++i) {
          fenwick_tree_populate(i, s[i]);
        }

        auto get_lca = [&](int u, int v) {
            if (is_ancestor(u, v)) return u;
            if (is_ancestor(v, u)) return v;
            
            for (int i = LOG - 1; i >= 0; --i) {
                if (!is_ancestor(up[u][i], v)) {
                    u = up[u][i];
                }
            }
            return up[u][0];
        };

        auto get_path_xor = [&](int u, int v) {
          int lca = get_lca(u, v);
          return tree.query(euler_in[u]) ^ tree.query(euler_in[v]) ^ char_bitmask(s[lca]);
        };

        auto update_node_value = [&](int node, char c) {
          fenwick_tree_populate(node, s[node]);
          s[node] = c;
          fenwick_tree_populate(node, s[node]);
        };

        // Handles: query u v
        auto handle_query = [&](int u, int v) -> bool {
            int path_xor = get_path_xor(u, v);
            
            // Palindrome check: at most one bit set
            return (path_xor == 0) || ((path_xor & (path_xor - 1)) == 0);
        };

        std::vector<bool> res;

        for (const string& q_str : queries) {
            stringstream ss(q_str);
            string type;
            ss >> type;

            if (type == "query") {
                int u, v;
                ss >> u >> v;
                res.push_back(handle_query(u, v));
            } 
            else if (type == "update") {
                int node;
                char c;
                ss >> node >> c;
                update_node_value(node, c);
            }
        }
        return res;
    }
};

int main() {
  // Input: n = 3, edges = [[0,1],[1,2]], s = "aac", queries = ["query 0 2","update 1 b","query 0 2"]
  int n = 3;
  vector<vector<int>> edges = {{0,1},{1,2}};
  string str = "aac";
  vector<string> queries = {"query 0 2","update 1 b","query 0 2"};
  cout << "Example 1 Output: [";
  Solution s;
  vector<bool> ans1 = s.palindromePath(n, edges, str, queries);
  for(int i=0; i<ans1.size(); ++i) cout << (ans1[i]?"true":"false") << (i==ans1.size()-1?"":",");
  cout << "]\n";

  // Example 2: n = 4, edges = [[0,1],[0,2],[0,3]], s = "abca", queries = ["query 1 2","update 0 b","query 2 3","update 3 a","query 1 3"]
  n = 4;
  edges = {{0,1},{0,2},{0,3}};
  str = "abca";
  queries = {"query 1 2","update 0 b","query 2 3","update 3 a","query 1 3"};
  cout << "Example 2 Output: [";
  vector<bool> ans2 = s.palindromePath(n, edges, str, queries);
  for(int i=0; i<ans2.size(); ++i) cout << (ans2[i]?"true":"false") << (i==ans2.size()-1?"":",");
  cout << "]\n";
}