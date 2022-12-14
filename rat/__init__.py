r"""

We've changed some stuff.

We've changed even more stuff.

We've changed stuff for a third time.

We've changed stuff for a fourth time.

We've changed stuff for a fifth time.

We've changed stuff for the sixth time.

We've changed stuff for the seventh time.

We've changed stuff for the eight time.

We've changed stuff for the nineth time.

Rat is an attempt to build an easy to use regression syntax, particularly
focused on player skill models. It is similar in theme to the many fine
regression packages (lm, lme4, rstanarm, brms, etc.), but tries to put
its own twist on the problem. It shares many features with more full featured
statistical packages (Stan, PyMC3, Turing, Bean Machine), but is for a
more constrained problem space than those.

Some central Rat features are:

1. Parameters are named explicitly
2. Parameters are defined by their use
3. Long-form dataframes are the data structure for everything (data and parameters)

Some central technical pieces are:

1. Rat uses a No-U-Turn-Sampler (following implementation in [Betancourt](https://arxiv.org/pdf/1701.02434.pdf))
2. Rat uses autodiff from [jax](https://github.com/google/jax)

Rat works in a limited language space to keep the backend stuff simple
(no sampling discrete parameters and no loops).

# Language

## Learning by Example

There are two full Rat examples included with the repo that are worth glancing at.
The first ([examples/mrp](https://github.com/bbbales2/regressions/tree/main/examples/mrp))
is an MRP example ported from
[MRP Case Studies](https://bookdown.org/jl5522/MRP-case-studies/introduction-to-mrp.html).

The second ([examples/fakeball](https://github.com/bbbales2/regressions/tree/main/examples/fakeball))
is an attempt to simulate some fake basketball-like data and estimate player on-off
effectiveness numbers.

The example folders contain information on how to run these models, but let us take
a quick glance at the fakeball example to at least expose ourselves to most of the features
Rat offers:

```
# We're modeling whether or not shots were made as a function of the time
#  varying skill of the five players playing offense and the five players
#  playing defense. `made`, `date`, `o0-o4`, and `d0-d4` come from one of
#  the input dataframes. o0-o4 and d0-d4 are names of the five players on
#  the floor playing offense and defense
made ~ bernoulli_logit(
    offense[o0, date] + offense[o1, date] + offense[o2, date] + offense[o3, date] + offense[o4, date] -
    (defense[d0, date] + defense[d1, date] + defense[d2, date] + defense[d3, date] + defense[d4, date])
);

# Offense and defense are represented as random walks with some initial condition
#  A second dataframe is passed to the program that contains the date for which every
#  player makes their first appearance
offense[player, date] = ifelse(first_appearance[player] == date, offense0[player], offense[player, shift(date, 1)] + epsilon_offense[player, date]);
defense[player, date] = ifelse(first_appearance[player] == date, defense0[player], defense[player, shift(date, 1)] + epsilon_defense[player, date]);

# These are centered parameterizations
offense0[player] ~ normal(0.0, tau0_offense);
defense0[player] ~ normal(0.0, tau0_defense);

epsilon_offense[player, date] ~ normal(0.0, tau_offense);
epsilon_defense[player, date] ~ normal(0.0, tau_defense);

# Some parameters have constraints!
tau_offense<lower = 0.0> ~ log_normal(0.0, 0.5);
tau_defense<lower = 0.0> ~ log_normal(0.0, 0.5);
tau0_offense<lower = 0.0> ~ log_normal(0.0, 0.5);
tau0_defense<lower = 0.0> ~ log_normal(0.0, 0.5);
```

Assuming we've saved appropriate data in a file `shots.csv`, then a model like this can
be run on the command-line (or from Python, but the command line is convenient for
this sort of thing):

```
rat fakeball.rat samples shots.csv first_appearance.csv
```

The output can be extracted and summarized in Python like:

```python
from rat.fit import load
import numpy

# Rat fits are serialized as parquet tables in folders
fit = load("samples")

# Each parameter is stored in its own table -- these can be joined together
# or summarized on their own
offense_df = fit.draws("offense")

# In this case we can build a table mapping player, date tuples to parameter
# summaries
offense_summary_df = (
    offense_df
    .groupby(["player", "date"])
    .agg(
        median=("offense", numpy.median),
        q10=("offense", lambda x: numpy.quantile(x, 0.1)),
        q90=("offense", lambda x: numpy.quantile(x, 0.9)),
    )
)
```

## Learning by Analogy

Rat builds on syntax and technology pioneered in a few different areas. To make the
connections clearer, we will call these connections out. Rat should be understood as
its own thing (learning by analogy is likely to be ineffective), but it was also
developed at a certain place and time and we believe the source material is enlightening.

Rat's *sampling* statements come from Stan:

```
y' ~ normal(a * x + b, sigma);
```

This would compile in a Stan model -- the thing you should notice though is the single
tick mark. In Stan that would mean transpose but in Rat that has to do with
vectorization. In Rat as in Stan, sampling statements increment a hidden unnormalized
log density variable (known as `target` in Stan). The statements themselves do
not actually lead to any sampling.

Rat uses dataframes as input, and by referencing columns of these dataframes Rat
programs can vectorize over them. This comes from the lm, lme4, brms, rstanarm world.

For instance, the above Rat program could be coupled with the dataframe:

```
 y, x
10, 1
15, 2
21, 3
24, 4
```

In this case, the sampling statement will accumulate four terms into the unnormalized
log density. In computing each term, the symbols `x` and `y` will be substituted with
values from the dataframe.

The same model could also be coupled with the following dataframe:

```
 y, x, sigma
10, 1,   1.1
15, 2,   2.0
21, 3,   1.7
24, 4,   0.9
```

In this case, the values for `sigma` would come from the dataframe as well.

This may lead you to ask, in any case, where do the values for `a` and `b` come from
(and `sigma` itself if we're using the first dataframe)?

We can see in the original sampling statement that there is enough information to
infer what `a`, `b`, and `sigma` are -- they are scalar parameters that we'll need
to do MCMC on.

How about something more complex? Let us estimate a logit scale win probability for a
group of teams based on some win loss data:

```
made, player
   0,  curry
   0,  curry
   1,  curry
   1,  green
   0,  thompson
   1,  thomspon
```

```
made' ~ bernoulli_logit(skill[player]);
```

In this case the syntax suggests that there is one `skill` parameter for each
player somewhere. Rat treats unresolved parameters like this like functions and
is in this way works similarly to Bean Machine.

This is more or less where learning by analogy ends for Rat

## Learning by Actually How It Works

Rat programs are written as a series of unordered *statements* of which there are
two types, *sampling* statements and *assignment* statements.

Sampling statements take the form of two expressions separated by a `~` and
assignments have a variable on the left hand side of an `=` and an expression
on the right hand side.

[It would be nice if we could write down our grammar and put it here]

Statements and expressions in Rat are always written in terms of scalars. There
is no concept of vectors exposed in the language (yet).

Vectorization in Rat comes from an understanding of primary variables. In every
statement there will be exactly one primary variable.

The rules for primary variable deduction are as follows (executed in order):

1. Search for all variables in a statement
2. If there is only one variable, that is the primary variable
3. If there are multiple variables, then one must be marked with ' to indicate
 it is the primary variable.

Vectorization proceeds in two directions, depending on if the primary variable
is associated with an input dataframe or not.

If the identifier of the primary variable can be found in one of the input dataframes,
then vectorization for a statement is done by executing that statement across
all rows of the input dataframe with column-values of the input dataframe
exposed as local variables that can be referenced by name in the calculation.

If the identifier of the primary variable is not found in an input dataframe, then it
is understood to be a function. Vectorization is handled by executing the statement
across the domain of the function and exposing the named arguments as local variables.

Function domains for variables not in dataframes are computed from their use. As part
of compiling a Rat program, Rat must compute the least fixed point function domain for
every variable that allows the program to execute. This is done by repeatedly
running a Rat program, recording what functions are called for what arguments,
and repeating this process until the domains of all functions have stabilized, reaching a fixed point.

It is entirely possible to write infinite recursions that make it impossible for
this calculation to succeed, since such fixed point does not exist. The compiler attempts to detect this problem by
trying to find a fixed point up to a set number of iterations, and will emit an error if it has not converged.

To make this process possible, control flow in Rat cannot depend on non-data variables.

Values for non-primary variables in statements can come from three places (searched in this order):
1. They can be exposed as local variables as part of the primary variable vectorization process
2. They can come from other input dataframes -- if the identifier matches a column in
  another input dataframe then the subscript arguments are used to look up a unique value
  (if there is no row or more than one row corresponding to the subscripts and error will
  be thrown)
3. They can come from nowhere (yet)! Variables that cannot be pulled from dataframes
  don't need values yet -- the Rat program can compile without them. These values are
  exposed by the compiler to the sampler which is then responsible for providing them, which are then treated as
  uninitialized parameters.
  It is on these values that control flow in a Rat program cannot depend, because they
  will not be available until after compilation, and Rat needs to know the control
  flow result at compilation to infer function domains.

==================

Rat syntax is built for writing vectorized calculations across dataframes. The idea
is that this is a useful framework for conceptualizing multilevel regressions, and
Rat tries to make it easy to do this in code.

Rat is made of *statements*. A statement in Rat consists of two *expressions* (the left hand side
and right hand side expressions) separated by either an `~` or an `=` and ending in `;`.
Those where the lefthand side and righthand side are separated by `~` are called sampling statements,
and those where the lefthand side and righthand side are separated by `=` are called assignments.
Expressions are composed of *functions* and *variable references* and do not contain any intervening `~`, `=`, or
`;` characters.

A statement can be multiple lines, and any line can end with a *comment* separated with `#`.
There are no multiline comments.

For example, this is a valid sampling statement in Rat:
```
score_diff' ~ normal( # It's a sampling statement!
    skill[home_team], # It's a regression with one group-level intercept!
    sigma);
```

Rat syntax vectorizes over dataframes. This means that each statement will produce code
that runs for each row in a dataframe. The dataframe that a statement vectorizes across is
called the *primary dataframe* -- there is exactly one primary dataframe per statement.

Rat statements resolve their primary dataframes in a process called *primary variable deduction*.
Every variable (a variable being a named symbol that is not a function) has exactly one dataframe
attached to it. To identify the primary dataframe, rat must identify the primary variable.

The rules for primary variable deduction are as follows (executed in order):

1. There can only be one primary variable in a statement.
2. If a variable reference is *primed*, then that variable is the primary variable.
3. If there is no primed variable references, then all variables with non-empty dataframes are treated as prime.
4. If there are no variables with non-empty dataframes, the leftmost one is the primary one.
5. It is an error if anything other than one primary variable is identified.
6. A *parameter* can only be used as the primary variable in one statement.

A variable reference can be primed if it ends with a `'`. A variable reference itself
is a variable name, an optional constraint, an optional sequence of *subscripts*, and an
followed by the optional prime symbol. In the example above, `score_diff`, `skill`, and
`sigma` are variable names. `home_team` is a subscript. `score_diff'`, `skill[home_team]`,
and `sigma` are the variable references, and `score_diff` is the primary variable.

Variables are associated with dataframes with the process of *variable dataframe deduction* (executed in order):

1. Variables with names that match columns in an *input dataframe* take that input dataframe
2. If variable names match columns in multiple input dataframes, it is an error
3. Otherwise, variables references are associated with parameters. The dataframe of the parameter is the minimum
dataframe required to execute all statements it is used in.

For the purposes of both dataframe deductions, Rat programs are understood top to bottom.

For the regression above, a suitable example of an input dataframe might be
(the point differentials for a number of NBA games from the 2016 season):

```
    game_id  home_score  away_score home_team away_team  score_diff  year
0         1         117          88       CLE       NYK        29.0  2016
1         2         113         104       POR       UTA         9.0  2016
2         3         100         129       GSW       SAS       -29.0  2016
3         4          96         108       ORL       MIA       -12.0  2016
4         5         130         121       IND       DAL         9.0  2016
5         6         122         117       BOS       BKN         5.0  2016
6         7         109          91       TOR       DET        18.0  2016
7         8          96         107       MIL       CHA       -11.0  2016
8         9         102          98       MEM       MIN         4.0  2016
9        10         102         107       NOP       DEN        -5.0  2016
10       11          97         103       PHI       CLE        -6.0  2016
```

Because `score_diff` matches a column in this dataframe, assuming there are no
other dataframes, this dataframe becomes the primary dataframe for this statement.
Because `skill` and `sigma` do not appear as columns in this dataframe, they
will be parameters.

The statement will *execute* once for each line of this dataframe. As the statement runs,
it will substitute values from this dataframe into variables and subscripts that match
column names.

In this case, that means there must be a value in `skill` corresponding to each
of the home teams (`CLE, POR, GSW, ORL, IND, BOS, TOR, MIL, MEM, PHI`). Because there
is one subscript, the `skill` dataframe will have one column. The values in that column
will be extended as necessary to allow all the `home_team` references.

Because `sigma` has no subscripts, the minimum dataframe necessary to support it is
the empty dataframe.

Execution for a sampling statement means evaluating and accumulating the log density
given by the name of the distribution on the right hand side of the `~`.

Execution of assignments is described in [Transformed Parameters](#transformed-parameters) and
[Shift operator](#shift-operator).

Considering the data, it may seem useful to predict the score differential of an NBA game
in terms of both teams' skills. A suitable model for this would be:
```
score_diff' ~ normal(skill[home_team] - skill[away_team], sigma);
```

In this statement, there is an extra variable reference, `skill[away_team]`. Because of
this, the `skill` dataframe will need to be extended to support all the away teams as well
(adding all the teams but `CLE`, which is already there).

## Transformed parameters

Modeling the `skill` parameter in the model above hierarchically with a non-centered
parameterization will be a good demonstration of assignment statements in Rat. As a reminder,
this sort of parameterization is useful for avoiding [divergences](https://mc-stan.org/users/documentation/case-studies/divergences_and_bias.html),
when doing MCMC using NUTS on multilevel models.

The non-centered parameterization takes the form:
```
score_diff' ~ normal(skill[home_team] - skill[away_team], sigma);
skill[team]' = skill_z[team] * tau;
skill_z ~ normal(0.0, 1.0);
```

For the second statement `skill` is the primary variable, so the dataframe defined implicitly
in the first statement will be the primary dataframe for the second line. Because of the subscript,
the parameter `skill_z` will be created with a non-empty dataframe. Because it has no subscript,
the parameter `tau` is created using the empty dataframe.

The subscript of `skill` is *renamed* to `team` by use as a primary variable. Because the subscript
is referenced by two names in the first statement, its name is ambiguous. Subscripts in a
primary variable reference are *renaming subscripts*. Because a parameter can only be used
as a primary variable once, this renaming only happens once. The renaming is necessary
for two reasons:
    
1. Rat needs the subscript to be named for output to work
2. Creating an underlying parameter `skill_z` for each `skill` requires that `skill_z` be
subscripted by the `skill` dataframe.

The assignment itself works by evaluating the expression on the right hand side and writing
the transformed parameter on the left (and the variable on the left hand side must
be a parameter, not data). Transformed parameters are immutable, so once they are set
they cannot be changed. All uses of a transformed parameter must preceed the assignment. This
may seem non-intuitive coming from other languages, but in Rat parameter use defines the
parameters themselves -- the assignment will simply guarantee that the necessary values
get set. Rat statements will effectively be executed in reverse order as they are written.

In the final statement the prior for `skill_z` is defined. Because `skill_z` is the only variable
in the statement, its dataframe will be the primary dataframe (and there is no need to prime it
manually). Because the use uniquely defines a name for the subscript, there is no need to rename it.

## Constraints

The model above won't get far without a prior on `tau`. Because `tau` is a
standard deviation, it must be constrained to be positive.

Rat adopts a similar constraint syntax to Stan:

```
score_diff' ~ normal(skill[home_team] - skill[away_team], sigma);
skill[team]' = skill_z[team] * tau;
skill_z ~ normal(0.0, 1.0);
tau<lower = 0.0> ~ normal(0.0, 1.0);
```

Constraints can only be used on parameters.

The constraint goes after the parameter name but before the subscripts. Rat
supports a `lower`, `upper` and a combination of the two constraints.

## Shift operator

The elements of Rat parameters are sorted with respect to the values of the
subscripts. The sorting is done by sorting the columns of the parameter
dataframe. This sorting is done in the order of the subscripts, so the
rightmost subscript is sorted last. The dataframes and parameter values having
a sorted order is covenient for time series data.

Going back to the basketball model, perhaps someone is interested in how a team's
skill changes year to year:

```
score_diff' ~ normal(skill[home_team, year] - skill[away_team, year], sigma);
skill[team, year]' = skill[team, shift(year, 1)] + skill_z[team] * tau;
skill_z ~ normal(0.0, 1.0);
tau<lower = 0.0> ~ normal(0.0, 1.0);
```

The first line still determines what the dataframe for `skill` will look like,
though now there will be two columns instead of one, with rows corresponding to
the necessary team-year combinations.

The second line is still an assignment, but it is different because the variable
assigned on the left hand side is used on the right hand side. The notation,
`skill[team, shift(year, 1)]` means, "take the skill corresponding to this
team in the previous year" (the shift behaves like the pandas
[shift](https://pandas.pydata.org/docs/reference/api/pandas.DataFrame.shift.html),
where a positive number means shift rows down the dataframe).

This works because:
1. Rat statements are executed across rows of the primary dataframe
2. The primary dataframe is sorted in ascending order according to its subscripts
3. The primary dataframe is already defined -- there is not problem of terminating
this recursive statement
4. Out-of-bounds accesses do not throw errors but instead return zero (the value
zero itself, not the zeroth element of the array)

Because of rules 1 and 2, when assigning a variable, it is possible to reference
the parts that have already been computed. Because of rules 3 and 4, there is no
problem with infinite recursions or edge cases.

For performance reasons when using recursive assignments:
1. There can be at most one shifted subscript
2. The shifted subscript must appear lasts

Currently for programmatic reasons, negative shifts are not allowed in recursive
assignments, though the goal is to allow this in the future.

### Simpler ways to shift

The shift operator used in a recursive assignment is the trickiest of the shifts.

The above model can also be written with a centered parameterization:
```
score_diff' ~ normal(skill[home_team, year] - skill[away_team, year], sigma);
skill[team, year]' ~ normal(skill[team, shift(year, 1)], tau);
tau<lower = 0.0> ~ normal(0.0, 1.0);
```

The difference here is that a sampling statement is not an assignment -- the parameters
here are parameters of the log density that the sampler explores. From a programmatic
perspective there is no recursion needed because the values for the parameters come
from somewhere else.

In this case, it is possible to shift on multiple subscripts and the shift can appear
on any subscript. These restrictions also aren't necessarys for non-recursive assignment.

### Shifts and groups

Shifts are done only within groups defined by the unshifted parameters. That is a mouthful,
but in terms of basketball example this looks like:

| `skill[team, year]` | `skill[team, shift(year, 1)]` |
| --------------------------------------------------- |
| `skill[CHA, 2016]`  | `0`                           |
| `skill[CHA, 2017]`  | `skill[CHA, 2016]`            |
| `skill[ATL, 2017]`  | `0`                           |

[WARNING: Currently negative shifts are not allowed in recursive assignments]

A negative shift produces a different result:

| `skill[team, year]` | `skill[team, shift(year, -1)]` |
| --------------------------------------------------- |
| `skill[CHA, 2016]`  | `skill[CHA, 2017]`            |
| `skill[CHA, 2017]`  | `0`                           |
| `skill[ATL, 2017]`  | `0`                           |

## Multiple input dataframes

A Rat program can take in multiple input dataframes. As a part of variable dataframe
deduction, every name will be associated with a dataframe (or an error will be thrown).

In the same way that parameters are handled, non-primary variable values are joined to
primary variables via subscripts. The major difference is that, because Rat allocates
parameter dataframes, it can be careful to avoid duplicate entries. Because dataframes
for data variables come from the outside, this must be verified by the user. It is an
error if rows in a dataframe are referenced in a way that makes them not unique.

As a simple example of using multiple dataframes, consider the eight schools data:
```
y,sigma,school
28,15,1
8,10,2
-3,16,3
7,11,4
-1,9,5
1,11,6
18,10,7
12,18,8
```

Along with the eight schools model:
```
y' ~ normal(theta[school], sigma);
theta' = mu + z[school] * tau;
z ~ normal(0, 1);
mu ~ normal(0, 5);
tau<lower = 0.0> ~ log_normal(0, 1);
```

In this case, it is possible to split the input dataframe in two, with one
dataframe for the `y` variable and one for `sigma`.

```
y,school    sigma,school
28,1        15,1
8,2         10,2
-3,3        16,3
7,4         11,4
-1,5        9,5
1,6         11,6
18,7        10,7
12,8        18,8
```

In this case the two dataframes could be joined together on `school`.

However, if instead these are passed as two separate dataframes to a Rat program, then
they can be recombined in code by replacing:

```
y' ~ normal(theta[school], sigma);
```

with

```
y' ~ normal(theta[school], sigma[school]);
```

The variable `sigma` uses the second dataframe because there is no `sigma` in the first,
and the subscript `school` allows the two sets of data to be joined together. It would be
an error for the subscript `school` to not be there. In that case the join from `sigma`
to `y` would not be unique.

## Sharp edges with renaming

Subscript values are determined by position, which means it is possible to rename variables
in a very misleading way.

```
score ~ normal(skill[team, year], sigma);
skill[year, team] ~ normal(all_time_skill[team], tau);
...
```

In the second line, the subscript names are reversed, which means that the values of
the `year` subscript on the second line will be the values of the `team` subscript on
the first line!

## Distributions

$\mathcal{R}$ here means all real numbers and $\mathcal{R}^+$ means real numbers greater than zero.


| Distribution | Constraints |
| ---------------------------|
| `y ~ bernoulli_logit(logit_p)` | $y = 0$ or $y = 1$, $\text{logit_p} \in \mathcal{R}$ |
| `y ~ cauchy(location, scale)` | $y, \text{location} \in \mathcal{R}$, $\text{scale} \in \mathcal{R}^+$ |
| `y ~ exponential(scale)` | $y, \text{scale} \in \mathcal{R}^+$ |
| `y ~ log_normal(mu, sigma)` | $\text{mu} \in \mathcal{R}$, $y, \text{sigma} \in \mathcal{R}^+$ |
| `y ~ normal(mu, sigma)` | $y, \text{mu} \in \mathcal{R}$, $\text{sigma} \in \mathcal{R}^+$ |

## Functions

* `abs(x)`
* `arccos(x)`
* `arcsin(x)`
* `arctan(x)`
* `ceil(x)`
* `cos(x)`
* `exp(x)`
* `floor(x)`
* `inverse_logit(x)`
* `log(x)`
* `logit(x)`
* `round(x)`
* `sin(x)`
* `tan(x)`

## Operator Precedence Table

|  Operator   |   Precedence   |
|------|:-----:|
| function calls(`exp`, `log`, etc.) | 100, leftmost derivative  |
| prefix negation(`-10`, `-(1+2)`, etc.) | 50 |
| `^`  | 40  |
| `*`, `/`, `%`  | 30  |
| `+`, `-`  | 10  |
| `>`, `<`, `>=`, `<=`, `!=`, `==` | 5  |

# Installation and Use

Rat is only available from Github, and requires [Rust](https://www.rust-lang.org/) to
be installed to work.

First, follow the [Rust installation directions](https://www.rust-lang.org/tools/install).

Secondly, install rat from Github:

```
git clone https://github.com/bbbales2/regressions
cd regressions
pip install .
```

## Command line interface

Rat is a Python library, but comes with a helper script `rat` to quickly compile and
run models.

For example, to fit a model `mrp.rat` with the data `mrp.csv` and save the results in
`output` we can do:

```
rat mrp.rat mrp.csv output
```

Type `rat -h` for full usage info.
"""

_todo_figure_out_internal_docs = """

---

## Internals - `rat.variables`, `rat.ops`, `rat.variables.Subscript`, and `rat.variables.SubscriptUse`
(This portion is for people who want to dig into rat's source)

If you look closely at rat's source, you might notice something weird: There's a `rat.ops.Param` class and a `rat.variables.Param`. This also goes for `rat.ops.Data`, `rat.ops.Subscript`. `rat.ops` is designated as elements for the nodes of the parse tree that's generated by the parser. Since rat uses the parse tree to transpile to Python, we need to inject additional information regarding subscripts to the parse tree. This is where `rat.variables` comes into play: they are used to hold information regarding subscripts for a given parameter. I'll use the [skill model](#subscripts) example to explain:

The parser converts the skill model above into the following parse tree representations:
```
ops.Normal(
    ops.Data("score_diff"),
    ops.Diff(
        ops.Param("skills", ops.Subscript(("home_team", "year"))),
        ops.Param("skills", ops.Subscript(("away_team", "year"))),
    ),
    ops.Param("sigma"),
),
ops.Normal(
    ops.Param("skills", ops.Subscript(("team", "year"))),
    ops.Param("skills_mu", ops.Subscript(("year",))),
    ops.Param("tau"),
),
ops.Normal(
    ops.Param("skills_mu", ops.Subscript(("year",))),
    ops.RealConstant(0.0),
    ops.RealConstant(1.0),
),
ops.Normal(
    ops.Param("tau", lower=ops.RealConstant(0.0)),
    ops.RealConstant(0.0),
    ops.RealConstant(1.0),
),
ops.Normal(
    ops.Param("sigma", lower=ops.RealConstant(0.0)),
    ops.RealConstant(0.0),
    ops.RealConstant(1.0),
)
```

For each parameter we create a `rat.variables.Subscript` object which in essence hold the factors of the subscript. Recall `skills[team, year]` was in fact `skills[union(home_team, away_team), year]`. So we need a parameter for each team-year combination. `rat.variables.Subscript` internally stores a dataframe with columns `team` and `year`, which hold these unique combinations as reference subscripts.

But we might want to just subscript `home_team` from `team`. That is, we might only want a portion of the subscript. `rat.variables.SubscriptUse` is the object that maps a variable's subscripts to another variable's reference subscript(its `rat.variables.Subscript` object). If we just wanted to subscript `home_team` from `team`, it will compare the `home_team` dataframe with `team`'s reference dataframe, and only select the combinations that are necessary.

---

## Language function reference
Below are individual links to supported math functions and distributions

- **Distributions**
    - `rat.ops.Normal` : `normal(mu, sigma)`
    - `rat.ops.BernoulliLogit`, `rat.compiler.bernoulli_logit` : `bernoulli_logit(p)`
    - `rat.ops.LogNormal`, `rat.compiler.log_normal`  : `log_normal(mu, sigma)`
    - `rat.ops.Cauchy`  : `cauchy(location, scale)`
    - `rat.ops.Exponential`  :  `exponential(scale)`
- **Functions**
    - `rat.ops.Log`: `log(x)`
    - `rat.ops.Exp` : `exp(x)`
    - `rat.ops.Abs` : `abs(x)`
    - `rat.ops.Floor` : `floor(x)`
    - `rat.ops.Ceil` : `ceil(x)`
    - `rat.ops.Round` : `round(x)`
    - `rat.ops.Sin` : `sin(x)`
    - `rat.ops.Cos` : `cos(x)`
    - `rat.ops.Tan` : `tan(x)`
    - `rat.ops.Arcsin` : `arcsin(x)`
    - `rat.ops.Arccos` : `arccos(x)`
    - `rat.ops.Arctan` : `arctan(x)`
    - `rat.ops.Logit` : `logit(x)`
    - `rat.ops.InverseLogit` : `inverse_logit(x)`

"""
