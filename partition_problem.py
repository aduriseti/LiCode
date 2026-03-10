def min_partition_score(nums, k):
    n = len(nums)
    prefix_sum = [0] * (n + 1)
    for i in range(n):
        prefix_sum[i + 1] = prefix_sum[i] + nums[i]

    def get_value(s):
        return s * (s + 1) // 2

    dp = [float("inf")] * (n + 1)

    for i in range(1, n + 1):
        dp[i] = get_value(prefix_sum[i])

    for j in range(2, k + 1):
        new_dp = [float("inf")] * (n + 1)
        for i in range(j, n + 1):
            for p in range(j - 1, i):
                current_sum = prefix_sum[i] - prefix_sum[p]
                score = dp[p] + get_value(current_sum)
                if score < new_dp[i]:
                    new_dp[i] = score
        dp = new_dp

    return dp[n]


if __name__ == "__main__":
    test_nums = [1, 2, 3]
    test_k = 2
    print(f"Test 1 (nums=[1,2,3], k=2): {min_partition_score(test_nums, test_k)}")

    test_nums2 = [7, 2, 5, 10, 8]
    test_k2 = 2
    print(f"Test 2 (nums=[7,2,5,10,8], k=2): {min_partition_score(test_nums2, test_k2)}")
